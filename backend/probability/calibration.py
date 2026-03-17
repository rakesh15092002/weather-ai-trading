"""Applies historical context to adjust raw probability estimates.

This module is intentionally simple:
- No external API calls
- No ML/AI libraries
- Pure Python math to blend raw LLM probabilities with historical hit rates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .reasoning_agent import ProbabilityEstimate


@dataclass(frozen=True)
class CalibrationResult:
    """Result of applying a simple calibration adjustment."""

    contract_id: str
    raw_probability: float
    calibrated_probability: float
    adjustment_applied: float
    calibration_source: str  # 'historical' or 'none'
    notes: str


def _clamp_probability(value: float) -> float:
    """Clamp a probability into [0.0, 1.0]."""
    return max(0.0, min(1.0, value))


def calibrate(
    estimate: ProbabilityEstimate,
    historical_hit_rate: Optional[float] = None,
) -> CalibrationResult:
    """Blend raw probability with optional historical hit-rate.

    Args:
        estimate: ProbabilityEstimate produced by the reasoning agent.
        historical_hit_rate: Optional empirical hit rate in [0.0, 1.0].

    Returns:
        CalibrationResult with calibrated probability and metadata.

    Raises:
        ValueError: If inputs are invalid.
    """
    if estimate is None:
        raise ValueError("estimate must not be None.")

    raw = _clamp_probability(float(estimate.estimated_probability))

    source = "none"
    notes = "No historical data provided; raw probability used as-is."
    calibrated = raw

    if historical_hit_rate is not None:
        if not (0.0 <= historical_hit_rate <= 1.0):
            raise ValueError(
                f"historical_hit_rate must be between 0.0 and 1.0, got {historical_hit_rate!r}."
            )

        hist = float(historical_hit_rate)
        calibrated = (raw * 0.6) + (hist * 0.4)
        calibrated = _clamp_probability(calibrated)
        source = "historical"
        notes = (
            "Calibrated using weighted blend: 60% raw model probability, 40% historical hit rate."
        )

    adjustment = calibrated - raw

    return CalibrationResult(
        contract_id=estimate.contract_id,
        raw_probability=raw,
        calibrated_probability=calibrated,
        adjustment_applied=adjustment,
        calibration_source=source,
        notes=notes,
    )

