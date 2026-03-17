"""Places orders on Kalshi and Polymarket (paper mode default).

Pure deterministic logic on our side:
- Paper trading mode by default (no real API calls)
- Optional live trading with Kalshi / Polymarket REST APIs
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Tuple
import os

import httpx
from dotenv import load_dotenv

from signal.signal_engine import TradeSignal
from risk.risk_engine import RiskDecision
from ingestion.market_client import MarketData


KALSHI_BASE_URL = "https://trading-api.kalshi.com/trade-api/v2"
POLYMARKET_BASE_URL = "https://clob.polymarket.com"


@dataclass(frozen=True)
class OrderResult:
    """Result of attempting to place an order on an exchange."""

    contract_id: str
    action: str
    units: int
    price: float
    status: str  # filled / rejected / paper_filled
    order_id: Optional[str]
    exchange: str
    filled_at: datetime
    notes: str


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _side_and_price_from_signal(signal: TradeSignal, market: MarketData) -> Tuple[str, float]:
    """Derive side ('yes'/'no') and limit price based on action."""
    if signal.action == "buy_yes":
        return "yes", float(market.yes_price)
    if signal.action == "buy_no":
        return "no", float(market.no_price)
    raise ValueError(f"Unsupported action '{signal.action}' for order placement.")


async def _place_kalshi_live_order(
    signal: TradeSignal,
    decision: RiskDecision,
    market: MarketData,
) -> Tuple[str, float]:
    """Place a live order on Kalshi and return (order_id, price).

    This is a minimal wrapper and may need to be adapted to Kalshi's full API spec.
    """
    load_dotenv()
    api_key = (os.getenv("KALSHI_API_KEY") or "").strip()
    if not api_key:
        raise ValueError("KALSHI_API_KEY is missing for live Kalshi trading.")

    side, price = _side_and_price_from_signal(signal, market)

    url = f"{KALSHI_BASE_URL}/orders"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    payload = {
        "ticker": signal.contract_id,
        "side": side.upper(),  # YES/NO
        "size": int(decision.adjusted_units),
        "price": int(round(price * 100)),  # cents
        "type": "LIMIT",
    }

    async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
        resp = await client.post(url, json=payload)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ValueError(
                f"Kalshi order placement failed with HTTP {exc.response.status_code}: {exc.response.text}"
            ) from exc

    data = resp.json()
    order_id = str(data.get("order_id") or data.get("id") or "")
    if not order_id:
        raise ValueError("Kalshi order response did not include an order ID.")

    return order_id, price


async def _place_polymarket_live_order(
    signal: TradeSignal,
    decision: RiskDecision,
    market: MarketData,
) -> Tuple[str, float]:
    """Place a live order on Polymarket and return (order_id, price).

    This is a simplified wrapper; adapt to Polymarket's authenticated CLOB API as needed.
    """
    load_dotenv()
    api_key = (os.getenv("POLYMARKET_API_KEY") or "").strip()
    if not api_key:
        raise ValueError("POLYMARKET_API_KEY is missing for live Polymarket trading.")

    side, price = _side_and_price_from_signal(signal, market)

    url = f"{POLYMARKET_BASE_URL}/orders"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    payload = {
        "marketId": market.contract_id,
        "side": side.upper(),  # YES/NO
        "size": int(decision.adjusted_units),
        "price": float(price),
        "type": "LIMIT",
    }

    async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
        resp = await client.post(url, json=payload)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ValueError(
                f"Polymarket order placement failed with HTTP {exc.response.status_code}: {exc.response.text}"
            ) from exc

    data = resp.json()
    order_id = str(data.get("order_id") or data.get("id") or "")
    if not order_id:
        raise ValueError("Polymarket order response did not include an order ID.")

    return order_id, price


async def place_order(
    signal: TradeSignal,
    decision: RiskDecision,
    market: MarketData,
    exchange: str,
    paper_trading: bool = True,
) -> OrderResult:
    """Place an order based on a trade signal and risk decision.

    Paper trading mode (default):
      - No external API calls
      - status = 'paper_filled'
      - order_id = 'PAPER-{contract_id}-{timestamp}'

    Live trading mode:
      - exchange='kalshi' → Kalshi REST API
      - exchange='polymarket' → Polymarket REST API
    """
    filled_at = _now_utc()
    exchange_norm = exchange.lower().strip()

    # Validate risk decision first.
    if not decision.approved or decision.adjusted_units <= 0:
        reason = decision.rejection_reason or "risk decision not approved"
        return OrderResult(
            contract_id=signal.contract_id,
            action=signal.action,
            units=0,
            price=0.0,
            status="rejected",
            order_id=None,
            exchange=exchange_norm,
            filled_at=filled_at,
            notes=reason,
        )

    # Determine side/price once.
    side, price = _side_and_price_from_signal(signal, market)

    if paper_trading:
        ts_str = filled_at.strftime("%Y%m%d%H%M%S")
        fake_id = f"PAPER-{signal.contract_id}-{ts_str}"
        return OrderResult(
            contract_id=signal.contract_id,
            action=signal.action,
            units=int(decision.adjusted_units),
            price=price,
            status="paper_filled",
            order_id=fake_id,
            exchange=exchange_norm,
            filled_at=filled_at,
            notes=f"Paper trade {side.upper()} executed at {price:.4f} for {decision.adjusted_units} units.",
        )

    # Live trading branch.
    if exchange_norm == "kalshi":
        order_id, live_price = await _place_kalshi_live_order(signal, decision, market)
    elif exchange_norm == "polymarket":
        order_id, live_price = await _place_polymarket_live_order(signal, decision, market)
    else:
        raise ValueError(f"Unsupported exchange '{exchange}'. Expected 'kalshi' or 'polymarket'.")

    return OrderResult(
        contract_id=signal.contract_id,
        action=signal.action,
        units=int(decision.adjusted_units),
        price=live_price,
        status="filled",
        order_id=order_id,
        exchange=exchange_norm,
        filled_at=filled_at,
        notes=f"Live trade {side.upper()} submitted at {live_price:.4f} for {decision.adjusted_units} units.",
    )

