"""Position sizing logic based on edge strength and confidence.

Pure deterministic rules:
- No OpenAI, no ML
- Simple mapping from net_edge + confidence to discrete units.
"""

from __future__ import annotations

from dataclasses import dataclass

from signal.signal_engine import TradeSignal


@dataclass(frozen=True)
class PositionSize:
    """Final position size in units for a given contract."""

    contract_id: str
    units: int
    sizing_reason: str
    net_edge: float
    confidence: str


def _base_units_from_edge(net_edge: float) -> tuple[int, str]:
    """Return base units and reason based purely on net_edge."""
    if net_edge < 0.04:
        return 0, "edge below threshold"
    if net_edge < 0.08:
        return 100, "moderate edge"
    if net_edge <= 0.14:
        return 150, "strong edge"
    return 200, "highest confidence"


def calculate_position_size(
    signal: TradeSignal,
) -> PositionSize:
    """Calculate deterministic position size from a TradeSignal."""
    confidence = str(signal.confidence).lower()
    net_edge = float(signal.net_edge)

    if signal.action == "no_trade":
        return PositionSize(
            contract_id=signal.contract_id,
            units=0,
            sizing_reason="no_trade signal",
            net_edge=net_edge,
            confidence=confidence,
        )

    base_units, reason = _base_units_from_edge(net_edge)

    if base_units == 0:
        return PositionSize(
            contract_id=signal.contract_id,
            units=0,
            sizing_reason=reason,
            net_edge=net_edge,
            confidence=confidence,
        )

    # Confidence override
    adjusted_units = base_units
    confidence_note = ""
    if confidence == "low":
        adjusted_units = int(base_units * 0.5)
        confidence_note = " with 50% reduction due to low confidence"
    elif confidence in {"medium", "high"}:
        # keep as is
        pass
    else:
        # Unexpected confidence label: be conservative.
        adjusted_units = int(base_units * 0.5)
        confidence_note = " with 50% reduction due to unknown confidence level"

    # Always round down and ensure non-negative.
    if adjusted_units < 0:
        adjusted_units = 0

    sizing_reason = reason + confidence_note

    return PositionSize(
        contract_id=signal.contract_id,
        units=adjusted_units,
        sizing_reason=sizing_reason,
        net_edge=net_edge,
        confidence=confidence,
    )


