"""Signal engine: calculate net edge and generate trade signals.

Pure Python only:
- No external API calls
- No ML/AI libraries
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from probability.buffer import FinalProbability
from ingestion.market_client import MarketData


@dataclass(frozen=True)
class TradeSignal:
    """Represents a trade decision for a single contract."""

    contract_id: str
    action: str  # buy_yes / buy_no / no_trade
    estimated_prob: float
    market_implied_prob: float
    raw_edge: float
    net_edge: float
    confidence: str
    position_units: int
    is_tradeable: bool
    rejection_reason: Optional[str]


def _position_size_from_edge(net_edge: float) -> int:
    """Map net edge to discrete position size."""
    if net_edge < 0.08:
        return 100
    if net_edge <= 0.14:
        return 150
    return 200


def generate_signal(
    final_prob: FinalProbability,
    market: MarketData,
    fees: float = 0.02,
    slippage: float = 0.01,
    spread_cost: float = 0.01,
    entry_threshold: float = 0.04,
) -> TradeSignal:
    """Generate a trade signal by comparing model probability vs market price.

    Args:
        final_prob: Output from probability.buffer.FinalProbability.
        market: Normalized market snapshot (MarketData).
        fees: Estimated total fee cost (in probability space).
        slippage: Expected adverse price movement.
        spread_cost: Half-spread cost.
        entry_threshold: Minimum net edge required to enter a trade.

    Returns:
        TradeSignal describing action, edge, and position size.
    """
    if final_prob is None:
        raise ValueError("final_prob must not be None.")
    if market is None:
        raise ValueError("market must not be None.")

    if not (0.0 <= market.yes_price <= 1.0):
        raise ValueError(f"market.yes_price must be in [0.0, 1.0], got {market.yes_price!r}.")

    estimated_prob = max(0.0, min(1.0, float(final_prob.final_probability)))
    market_implied = float(market.yes_price)

    raw_edge = estimated_prob - market_implied
    net_edge = raw_edge - float(fees) - float(slippage) - float(spread_cost)

    is_tradeable = bool(final_prob.is_tradeable)
    rejection_reason: Optional[str] = None
    action = "no_trade"
    position_units = 0

    if not is_tradeable:
        rejection_reason = "contract not tradeable due to lead time or other constraints"
    elif net_edge < entry_threshold:
        rejection_reason = (
            f"net_edge {net_edge:.4f} is below entry_threshold {entry_threshold:.4f}"
        )
    else:
        # We have sufficient net edge; decide side.
        if raw_edge > 0:
            action = "buy_yes"
        elif raw_edge < 0:
            action = "buy_no"
        else:
            # Zero raw edge is not worth trading.
            rejection_reason = "raw_edge is zero; no directional advantage"

        if action != "no_trade":
            position_units = _position_size_from_edge(net_edge)
        else:
            is_tradeable = False

    confidence = getattr(final_prob, "calibrated_probability", estimated_prob)

    return TradeSignal(
        contract_id=final_prob.contract_id,
        action=action,
        estimated_prob=estimated_prob,
        market_implied_prob=market_implied,
        raw_edge=raw_edge,
        net_edge=net_edge,
        confidence=f"{confidence:.3f}",
        position_units=position_units,
        is_tradeable=is_tradeable and action != "no_trade" and position_units > 0,
        rejection_reason=rejection_reason,
    )

