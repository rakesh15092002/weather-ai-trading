"""Risk engine: enforces hard risk limits and kill switch.

Pure deterministic rules:
- No OpenAI
- No ML/AI libraries
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional

from signal.signal_engine import TradeSignal
from ingestion.market_client import MarketData


@dataclass(frozen=True)
class RiskState:
    """Tracks running P&L and exposure for risk checks."""

    daily_loss: float = 0.0
    weekly_loss: float = 0.0
    city_exposure: Dict[str, int] = field(default_factory=dict)
    trades_today: List[Dict[str, object]] = field(default_factory=list)
    is_killed: bool = False
    kill_reason: Optional[str] = None

    # Hard-coded limits
    MAX_LOSS_DAILY: float = 500.0
    MAX_LOSS_WEEKLY: float = 2500.0
    MAX_CITY_EXPOSURE: int = 200
    MAX_UNITS: int = 200
    DATA_STALE_MINUTES: int = 30


@dataclass(frozen=True)
class RiskDecision:
    """Result of a risk check for a proposed trade."""

    approved: bool
    rejection_reason: Optional[str]
    adjusted_units: int
    warnings: List[str]


def trigger_kill(state: RiskState, reason: str) -> RiskState:
    """Trigger global kill switch with a clear reason."""
    if not reason:
        reason = "kill switch activated"
    return replace(state, is_killed=True, kill_reason=reason)


def reset_daily(state: RiskState) -> RiskState:
    """Reset daily stats at start of a new trading day."""
    return replace(state, daily_loss=0.0, trades_today=[])


def update_state_on_loss(state: RiskState, loss_units: float) -> RiskState:
    """Update running P&L after a realized loss.

    loss_units is interpreted as currency loss, not contracts.
    """
    if loss_units < 0:
        raise ValueError(f"loss_units must be non-negative, got {loss_units!r}.")

    new_daily = state.daily_loss + loss_units
    new_weekly = state.weekly_loss + loss_units

    updated = replace(state, daily_loss=new_daily, weekly_loss=new_weekly)

    # Auto-kill if limits breached.
    if new_daily >= state.MAX_LOSS_DAILY:
        return trigger_kill(updated, "daily loss limit breached")
    if new_weekly >= state.MAX_LOSS_WEEKLY:
        return trigger_kill(updated, "weekly loss limit breached")

    return updated


def update_state_on_fill(
    state: RiskState,
    city: str,
    units: int,
    contract_id: str,
) -> RiskState:
    """Update exposure and trade log after a fill."""
    if units < 0:
        raise ValueError(f"units must be non-negative, got {units!r}.")

    city_key = city.upper()
    current = state.city_exposure.get(city_key, 0)
    new_exposure = current + units

    new_city_exposure = dict(state.city_exposure)
    new_city_exposure[city_key] = new_exposure

    new_trades = list(state.trades_today)
    new_trades.append(
        {
            "city": city_key,
            "units": units,
            "contract_id": contract_id,
        }
    )

    return replace(state, city_exposure=new_city_exposure, trades_today=new_trades)


def _available_city_capacity(state: RiskState, city: str) -> int:
    """Return remaining capacity for the given city in units."""
    city_key = city.upper()
    used = state.city_exposure.get(city_key, 0)
    remaining = state.MAX_CITY_EXPOSURE - used
    return max(0, remaining)


def check_risk(
    signal: TradeSignal,
    market: MarketData,
    city: str,
    state: RiskState,
) -> RiskDecision:
    """Evaluate whether a proposed trade signal passes risk checks.

    Rejection rules (in order):
      1. Global kill switch active
      2. signal.action == 'no_trade'
      3. daily_loss >= MAX_LOSS_DAILY
      4. weekly_loss >= MAX_LOSS_WEEKLY
      5. city exposure >= MAX_CITY_EXPOSURE
      6. market.liquidity_score == 'low'

    Units are adjusted downwards to respect MAX_UNITS and remaining city capacity.
    """
    warnings: List[str] = []

    if state.is_killed:
        return RiskDecision(
            approved=False,
            rejection_reason=state.kill_reason or "global kill switch active",
            adjusted_units=0,
            warnings=warnings,
        )

    if signal.action == "no_trade":
        return RiskDecision(
            approved=False,
            rejection_reason="signal indicates no_trade",
            adjusted_units=0,
            warnings=warnings,
        )

    if state.daily_loss >= state.MAX_LOSS_DAILY:
        return RiskDecision(
            approved=False,
            rejection_reason="daily loss limit reached",
            adjusted_units=0,
            warnings=warnings,
        )

    if state.weekly_loss >= state.MAX_LOSS_WEEKLY:
        return RiskDecision(
            approved=False,
            rejection_reason="weekly loss limit reached",
            adjusted_units=0,
            warnings=warnings,
        )

    city_capacity = _available_city_capacity(state, city)
    if city_capacity <= 0:
        return RiskDecision(
            approved=False,
            rejection_reason=f"city exposure limit reached for {city.upper()}",
            adjusted_units=0,
            warnings=warnings,
        )

    if str(market.liquidity_score).lower() == "low":
        return RiskDecision(
            approved=False,
            rejection_reason="market liquidity is low; trade rejected",
            adjusted_units=0,
            warnings=warnings,
        )

    # If we reach here, the trade is eligible in principle; cap units.
    requested = max(0, int(signal.position_units))
    if requested == 0:
        return RiskDecision(
            approved=False,
            rejection_reason="signal requested 0 units",
            adjusted_units=0,
            warnings=warnings,
        )

    approved_units = min(requested, city_capacity, state.MAX_UNITS)

    if approved_units < requested:
        warnings.append(
            f"position size reduced from {requested} to {approved_units} due to risk limits"
        )

    if approved_units <= 0:
        return RiskDecision(
            approved=False,
            rejection_reason="no capacity left after applying risk limits",
            adjusted_units=0,
            warnings=warnings,
        )

    return RiskDecision(
        approved=True,
        rejection_reason=None,
        adjusted_units=approved_units,
        warnings=warnings,
    )

