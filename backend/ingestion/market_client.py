"""Fetches Kalshi and Polymarket prices and order book.

This module provides thin async clients around the Kalshi and Polymarket APIs
and normalizes their responses into a common MarketData dataclass.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from dotenv import load_dotenv
import os


KALSHI_BASE_URL = "https://trading-api.kalshi.com/trade-api/v2"
POLYMARKET_BASE_URL = "https://clob.polymarket.com"


@dataclass(frozen=True)
class MarketData:
    """Normalized market snapshot from a prediction market venue."""

    contract_id: str
    yes_price: float  # 0.0 to 1.0
    no_price: float   # 0.0 to 1.0
    spread: float
    volume_24h: float
    liquidity_score: str  # high / medium / low


def _liquidity_from_volume(volume_24h: float) -> str:
    """Map 24h volume to a human-readable liquidity score."""
    if volume_24h > 5000:
        return "high"
    if 500 <= volume_24h <= 5000:
        return "medium"
    return "low"


def _safe_price(value: Any) -> float:
    """Convert raw API price value (often cents) into 0–1 float."""
    if value is None:
        raise ValueError("Missing price value in market response.")
    return float(value)


async def fetch_kalshi_market(
    contract_id: str,
    api_key: str,
) -> MarketData:
    """Fetch best bid/ask and volume for a Kalshi contract.

    Args:
        contract_id: Kalshi market ticker / contract identifier.
        api_key: Optional explicit Kalshi API key. If empty, falls back to
            KALSHI_API_KEY from environment (.env via python-dotenv).

    Returns:
        MarketData snapshot for the specified Kalshi contract.

    Raises:
        ValueError: For configuration / response issues with clear messages.
    """
    load_dotenv()

    key = (api_key or "").strip() or (os.getenv("KALSHI_API_KEY") or "").strip()
    if not key:
        # Paper trading mode: return deterministic mock data if no key is available.
        # This allows the rest of the pipeline to run without live credentials.
        base = (abs(hash(contract_id)) % 30) / 100.0  # 0.00 - 0.29
        yes_price = min(max(0.35 + base, 0.0), 1.0)
        no_price = 1.0 - yes_price
        volume_24h = float(100 + (abs(hash(contract_id + ":vol")) % 800))  # 100 - 899
        return MarketData(
            contract_id=contract_id,
            yes_price=yes_price,
            no_price=no_price,
            spread=0.02,
            volume_24h=volume_24h,
            liquidity_score=_liquidity_from_volume(volume_24h),
        )

    headers = {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }

    # We attempt to fetch both market summary and order book.
    market_url = f"{KALSHI_BASE_URL}/markets/{contract_id}"
    orderbook_url = f"{KALSHI_BASE_URL}/markets/{contract_id}/orderbook"

    async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
        try:
            market_resp = await client.get(market_url)
            market_resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ValueError(
                f"Kalshi market request failed for contract_id='{contract_id}' "
                f"with HTTP {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ValueError(f"Failed to reach Kalshi API for contract_id='{contract_id}': {exc}") from exc

        try:
            ob_resp = await client.get(orderbook_url)
            ob_resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ValueError(
                f"Kalshi orderbook request failed for contract_id='{contract_id}' "
                f"with HTTP {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ValueError(
                f"Failed to reach Kalshi orderbook API for contract_id='{contract_id}': {exc}"
            ) from exc

    market_json: dict[str, Any] = market_resp.json()
    ob_json: dict[str, Any] = ob_resp.json()

    # Kalshi typically returns prices in cents [0,100]; convert to 0–1.
    volume_24h_raw = market_json.get("volume_24h") or market_json.get("volume")
    if volume_24h_raw is None:
        raise ValueError(f"Kalshi response missing 24h volume for contract_id='{contract_id}'.")
    volume_24h = float(volume_24h_raw)

    yes_best_bid = ob_json.get("yes_best_bid")
    yes_best_ask = ob_json.get("yes_best_ask")
    no_best_bid = ob_json.get("no_best_bid")
    no_best_ask = ob_json.get("no_best_ask")

    # Fallbacks: if side-specific not present, try generic best bid/ask.
    if yes_best_bid is None:
        yes_best_bid = ob_json.get("best_bid_yes")
    if yes_best_ask is None:
        yes_best_ask = ob_json.get("best_ask_yes")
    if no_best_bid is None:
        no_best_bid = ob_json.get("best_bid_no")
    if no_best_ask is None:
        no_best_ask = ob_json.get("best_ask_no")

    if yes_best_ask is None and yes_best_bid is None:
        raise ValueError(f"Kalshi orderbook missing YES prices for contract_id='{contract_id}'.")
    if no_best_ask is None and no_best_bid is None:
        raise ValueError(f"Kalshi orderbook missing NO prices for contract_id='{contract_id}'.")

    # Use mid-price when both bid and ask exist; otherwise, use whichever is present.
    def mid_or_single(bid: Any, ask: Any) -> float:
        if bid is not None and ask is not None:
            return (_safe_price(bid) + _safe_price(ask)) / 2.0
        if bid is not None:
            return _safe_price(bid)
        return _safe_price(ask)

    yes_price_cents = mid_or_single(yes_best_bid, yes_best_ask)
    no_price_cents = mid_or_single(no_best_bid, no_best_ask)

    yes_price = yes_price_cents / 100.0
    no_price = no_price_cents / 100.0

    spread = abs(yes_price - (1.0 - no_price))

    liquidity_score = _liquidity_from_volume(volume_24h)

    return MarketData(
        contract_id=contract_id,
        yes_price=yes_price,
        no_price=no_price,
        spread=spread,
        volume_24h=volume_24h,
        liquidity_score=liquidity_score,
    )


async def fetch_polymarket_market(
    condition_id: str,
) -> MarketData:
    """Fetch best prices and volume for a Polymarket condition.

    Args:
        condition_id: Polymarket condition identifier.

    Returns:
        MarketData snapshot for the specified Polymarket condition.

    Raises:
        ValueError: For response / parsing issues with clear messages.
    """
    markets_url = f"{POLYMARKET_BASE_URL}/markets"
    params = {"conditionId": condition_id}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(markets_url, params=params)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ValueError(
                f"Polymarket markets request failed for condition_id='{condition_id}' "
                f"with HTTP {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ValueError(f"Failed to reach Polymarket API for condition_id='{condition_id}': {exc}") from exc

    payload = resp.json()
    markets = payload if isinstance(payload, list) else payload.get("markets")
    if not markets:
        raise ValueError(f"No Polymarket markets found for condition_id='{condition_id}'.")

    # For now, take the first market associated with this condition.
    market = markets[0]
    contract_id = market.get("id") or market.get("marketId") or condition_id

    # Polymarket prices are often expressed in [0,1] already under "yesPrice"/"noPrice" or "pYes"/"pNo".
    yes_raw = (
        market.get("yesPrice")
        or market.get("pYes")
        or (market.get("outcomes", [{}])[0].get("price") if market.get("outcomes") else None)
    )
    no_raw = market.get("noPrice") or market.get("pNo")

    if yes_raw is None:
        raise ValueError(f"Polymarket market missing YES price for condition_id='{condition_id}'.")

    yes_price = float(yes_raw)
    if no_raw is not None:
        no_price = float(no_raw)
    else:
        # Derive NO price if not present.
        no_price = 1.0 - yes_price

    volume_24h_raw = (
        market.get("volume24h")
        or market.get("volume_24h")
        or market.get("volume")
    )
    if volume_24h_raw is None:
        raise ValueError(f"Polymarket market missing 24h volume for condition_id='{condition_id}'.")
    volume_24h = float(volume_24h_raw)

    spread = abs(yes_price - (1.0 - no_price))
    liquidity_score = _liquidity_from_volume(volume_24h)

    return MarketData(
        contract_id=str(contract_id),
        yes_price=yes_price,
        no_price=no_price,
        spread=spread,
        volume_24h=volume_24h,
        liquidity_score=liquidity_score,
    )

