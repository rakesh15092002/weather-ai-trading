"""Applies lead-time based error buffer to the calibrated probability.

Pure Python only:
- No external API calls
- No ML/AI libraries
"""

from __future__ import annotations

from dataclasses import dataclass

from .calibration import CalibrationResult


@dataclass(frozen=True)
class FinalProbability:
    """Final trade-ready probability after applying lead-time buffer."""

    contract_id: str
    calibrated_probability: float
    buffer_applied: float
    final_probability: float
    lead_hours: int
    month: int
    is_tradeable: bool


def _clamp_probability(value: float) -> float:
    """Clamp probability into [0.0, 1.0]."""
    return max(0.0, min(1.0, value))


def _buffer_for_lead(lead_hours: int) -> float:
    """Determine error buffer based on lead time in hours."""
    if lead_hours < 0:
        raise ValueError(f"lead_hours must be non-negative, got {lead_hours!r}.")

    if lead_hours <= 12:
        return 0.04
    if lead_hours <= 24:
        return 0.065
    if lead_hours <= 48:
        return 0.10
    return 0.15


def apply_buffer(
    calibration: CalibrationResult,
    lead_hours: int,
    month: int,
) -> FinalProbability:
    """Apply a lead-time based buffer to a calibrated probability.

    Args:
        calibration: Result from the calibration step.
        lead_hours: Lead time in hours between now and settlement.
        month: Month number (1–12) for optional downstream seasonality logic.

    Returns:
        FinalProbability with buffer and tradeability flag.

    Raises:
        ValueError: If inputs are invalid.
    """
    if calibration is None:
        raise ValueError("calibration must not be None.")

    if not (1 <= month <= 12):
        raise ValueError(f"month must be between 1 and 12, got {month!r}.")

    buffer = _buffer_for_lead(lead_hours)

    calibrated = _clamp_probability(float(calibration.calibrated_probability))
    final = _clamp_probability(calibrated - buffer)

    tradeable = lead_hours <= 48 and final > 0.0

    if lead_hours > 48:
        # Explicitly mark as non-tradeable regardless of final probability.
        tradeable = False

    return FinalProbability(
        contract_id=calibration.contract_id,
        calibrated_probability=calibrated,
        buffer_applied=buffer,
        final_probability=final,
        lead_hours=lead_hours,
        month=month,
        is_tradeable=tradeable,
    )

