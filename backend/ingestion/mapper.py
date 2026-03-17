"""Maps contract_id to exact station lat/lon, timezone, and settlement rules.

This module is intentionally pure/static:
- No external API calls
- No ML/AI logic
- Maintains an in-memory canonical mapping table for contract specifications
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ContractSpec:
    """Canonical contract specification mapped to a weather station."""

    exchange: str
    contract_id: str
    station_name: str
    station_lat: float
    station_lon: float
    timezone: str
    settlement_day: str
    settlement_rule: str
    event_definition: str
    threshold_f: float
    comparison: str  # gte / lte


# Canonical static mapping: contract_id -> ContractSpec
STATION_MAP: Dict[str, ContractSpec] = {
    "NYC-HIGH-75-2026-07-10": ContractSpec(
        exchange="kalshi",
        contract_id="NYC-HIGH-75-2026-07-10",
        station_name="JFK Airport",
        station_lat=40.6413,
        station_lon=-73.7781,
        timezone="America/New_York",
        settlement_day="2026-07-10",
        settlement_rule="daily_high_f",
        event_definition="Daily high temperature at JFK Airport is >= 75F on 2026-07-10 (local time).",
        threshold_f=75.0,
        comparison="gte",
    ),
    "NYC-HIGH-80-2026-07-15": ContractSpec(
        exchange="kalshi",
        contract_id="NYC-HIGH-80-2026-07-15",
        station_name="JFK Airport",
        station_lat=40.6413,
        station_lon=-73.7781,
        timezone="America/New_York",
        settlement_day="2026-07-15",
        settlement_rule="daily_high_f",
        event_definition="Daily high temperature at JFK Airport is >= 80F on 2026-07-15 (local time).",
        threshold_f=80.0,
        comparison="gte",
    ),
    "CHI-HIGH-90-2026-07-20": ContractSpec(
        exchange="kalshi",
        contract_id="CHI-HIGH-90-2026-07-20",
        station_name="OHare Airport",
        station_lat=41.9742,
        station_lon=-87.9073,
        timezone="America/Chicago",
        settlement_day="2026-07-20",
        settlement_rule="daily_high_f",
        event_definition="Daily high temperature at OHare Airport is >= 90F on 2026-07-20 (local time).",
        threshold_f=90.0,
        comparison="gte",
    ),
    "MIA-HIGH-95-2026-08-01": ContractSpec(
        exchange="kalshi",
        contract_id="MIA-HIGH-95-2026-08-01",
        station_name="Miami Airport",
        station_lat=25.7959,
        station_lon=-80.2870,
        timezone="America/New_York",
        settlement_day="2026-08-01",
        settlement_rule="daily_high_f",
        event_definition="Daily high temperature at Miami Airport is >= 95F on 2026-08-01 (local time).",
        threshold_f=95.0,
        comparison="gte",
    ),
}


def get_contract(contract_id: str) -> Optional[ContractSpec]:
    """Return the ContractSpec for a given contract_id, or None if missing."""
    return STATION_MAP.get(contract_id)


def get_city_from_contract(contract_id: str) -> str:
    """Extract the city code from the contract_id (substring before first '-')."""
    if not contract_id or "-" not in contract_id:
        raise ValueError(f"Invalid contract_id '{contract_id}'. Expected format like 'NYC-HIGH-75-YYYY-MM-DD'.")
    return contract_id.split("-", 1)[0]


def list_active_contracts() -> List[str]:
    """List all active contract IDs currently registered in STATION_MAP."""
    return sorted(STATION_MAP.keys())


def add_contract(spec: ContractSpec) -> None:
    """Add or overwrite a contract spec at runtime."""
    if not spec.contract_id:
        raise ValueError("ContractSpec.contract_id cannot be empty.")
    STATION_MAP[spec.contract_id] = spec


