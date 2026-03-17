"""Checks if ingested data is stale and triggers a kill switch.

This module is pure/static:
- No external API calls
- No ML/AI logic
- Uses UTC timestamps only via datetime.now(timezone.utc)
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple


@dataclass(frozen=True)
class FreshnessState:
    """Tracks data freshness and whether the system is killed (trading halted)."""

    last_weather_fetch: Optional[datetime] = None
    last_market_fetch: Optional[datetime] = None
    is_killed: bool = False
    kill_reason: Optional[str] = None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def trigger_kill_switch(state: FreshnessState, reason: str) -> FreshnessState:
    """Kill trading immediately with a human-readable reason."""
    if not reason:
        reason = "kill switch triggered"
    return replace(state, is_killed=True, kill_reason=reason)


def reset_kill_switch(state: FreshnessState) -> FreshnessState:
    """Reset kill switch back to safe (does not update fetch timestamps)."""
    return replace(state, is_killed=False, kill_reason=None)


def update_weather_fetch(state: FreshnessState) -> FreshnessState:
    """Update weather fetch timestamp to now (UTC)."""
    return replace(state, last_weather_fetch=_now_utc())


def update_market_fetch(state: FreshnessState) -> FreshnessState:
    """Update market fetch timestamp to now (UTC)."""
    return replace(state, last_market_fetch=_now_utc())


def check_weather_freshness(state: FreshnessState, max_age_minutes: int = 30) -> bool:
    """Check weather freshness and auto-trigger kill switch if stale.

    Returns:
        True if weather data is fresh enough, otherwise False.
    """
    if state.is_killed:
        return False

    if state.last_weather_fetch is None:
        return False

    age = _now_utc() - state.last_weather_fetch
    if age > timedelta(minutes=max_age_minutes):
        return False

    return True


def check_market_freshness(state: FreshnessState, max_age_minutes: int = 10) -> bool:
    """Check market freshness and auto-trigger kill switch if stale.

    Returns:
        True if market data is fresh enough, otherwise False.
    """
    if state.is_killed:
        return False

    if state.last_market_fetch is None:
        return False

    age = _now_utc() - state.last_market_fetch
    if age > timedelta(minutes=max_age_minutes):
        return False

    return True


def is_safe_to_trade(state: FreshnessState) -> Tuple[bool, str]:
    """Return whether it is safe to trade and a reason string.

    The function also enforces rules:
    - Weather stale if older than 30 minutes
    - Market stale if older than 10 minutes
    - If stale, kill switch is considered active
    """
    if state.is_killed:
        return False, state.kill_reason or "killed"

    now = _now_utc()

    if state.last_weather_fetch is None:
        return False, "weather data has never been fetched"
    if now - state.last_weather_fetch > timedelta(minutes=30):
        return False, "weather data is stale (>30 minutes)"

    if state.last_market_fetch is None:
        return False, "market data has never been fetched"
    if now - state.last_market_fetch > timedelta(minutes=10):
        return False, "market data is stale (>10 minutes)"

    return True, "ok"


