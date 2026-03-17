"""Monitors open trades and decides when to exit based on profit targets.

Pure deterministic rules:
- No external API calls
- No ML/AI libraries
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone


@dataclass(frozen=True)
class OpenTrade:
    """Represents an open position in a single contract."""

    contract_id: str
    action: str
    units: int
    entry_price: float
    current_price: float
    entry_time: datetime
    exchange: str
    order_id: str | None


@dataclass(frozen=True)
class ExitDecision:
    """Represents an exit decision for an open trade."""

    contract_id: str
    should_exit: bool
    units_to_exit: int
    exit_reason: str
    current_pnl_pct: float


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def calculate_pnl(trade: OpenTrade) -> float:
    """Calculate current PnL percentage for a trade."""
    if trade.entry_price <= 0:
        raise ValueError(f"entry_price must be positive, got {trade.entry_price!r}.")

    pnl_pct = (trade.current_price - trade.entry_price) / trade.entry_price * 100.0
    return pnl_pct


def update_trade_price(trade: OpenTrade, new_price: float) -> OpenTrade:
    """Return a new OpenTrade with updated current_price."""
    if new_price < 0:
        raise ValueError(f"new_price must be non-negative, got {new_price!r}.")
    return replace(trade, current_price=new_price)


def check_exit(
    trade: OpenTrade,
    current_price: float,
) -> ExitDecision:
    """Decide whether to exit an open trade based on profit / loss thresholds.

    Exit rules:
    - pnl_pct >= 150 → exit remaining 50% units, reason='profit_target_150pct'
    - pnl_pct >= 100 → exit 50% units, reason='profit_target_100pct'
    - pnl_pct <= -50 → exit all units, reason='stop_loss'
    - Otherwise → no exit
    """
    if trade.units <= 0:
        return ExitDecision(
            contract_id=trade.contract_id,
            should_exit=False,
            units_to_exit=0,
            exit_reason="no_units_open",
            current_pnl_pct=0.0,
        )

    updated_trade = update_trade_price(trade, current_price)
    pnl_pct = calculate_pnl(updated_trade)

    # Stop-loss check first to prioritize risk reduction.
    if pnl_pct <= -50.0:
        return ExitDecision(
            contract_id=trade.contract_id,
            should_exit=True,
            units_to_exit=updated_trade.units,
            exit_reason="stop_loss",
            current_pnl_pct=pnl_pct,
        )

    # Profit targets
    half_units = max(1, updated_trade.units // 2)

    if pnl_pct >= 150.0:
        return ExitDecision(
            contract_id=trade.contract_id,
            should_exit=True,
            units_to_exit=half_units,
            exit_reason="profit_target_150pct",
            current_pnl_pct=pnl_pct,
        )

    if pnl_pct >= 100.0:
        return ExitDecision(
            contract_id=trade.contract_id,
            should_exit=True,
            units_to_exit=half_units,
            exit_reason="profit_target_100pct",
            current_pnl_pct=pnl_pct,
        )

    return ExitDecision(
        contract_id=trade.contract_id,
        should_exit=False,
        units_to_exit=0,
        exit_reason="hold",
        current_pnl_pct=pnl_pct,
    )

