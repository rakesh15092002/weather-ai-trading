"""Uses OpenAI API (gpt-4o) to estimate probability of a weather contract event.

This module:
- Takes structured forecast + contract spec inputs
- Calls OpenAI Chat Completions with a JSON-only instruction
- Parses the JSON into a ProbabilityEstimate dataclass
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
import json
import os

from dotenv import load_dotenv
from openai import AsyncOpenAI, OpenAIError

from ingestion.weather_client import ForecastData
from ingestion.mapper import ContractSpec


MODEL_NAME = "gpt-4o"


@dataclass(frozen=True)
class ProbabilityEstimate:
    """Structured probability estimate returned by the LLM."""

    contract_id: str
    estimated_probability: float  # 0.0 to 1.0
    confidence_level: str  # high / medium / low
    forecast_error_buffer: float
    uncertainty_range_low: float
    uncertainty_range_high: float
    reasoning_summary: str
    raw_openai_response: str


def _load_client() -> AsyncOpenAI:
    """Load OpenAI async client using python-dotenv."""
    load_dotenv()
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY is missing. Set it in your environment or .env file."
        )
    return AsyncOpenAI(api_key=api_key)


def _buffer_from_lead_hours(lead_hours: int) -> float:
    """Derive a default forecast error buffer based on rules."""
    if lead_hours <= 12:
        # 0.03–0.05 → take mid-point
        return 0.04
    if lead_hours <= 24:
        # 0.05–0.08
        return 0.065
    if lead_hours <= 48:
        # 0.08–0.12
        return 0.10
    # Beyond 48h is discouraged; pick a conservative buffer
    return 0.15


def _build_system_prompt() -> str:
    return (
        "You are an expert weather prediction market analyst. "
        "Given a weather forecast and a prediction market contract definition, "
        "you estimate the probability that the contract resolves YES.\n\n"
        "Return ONLY a single valid JSON object with these exact keys:\n"
        "- estimated_probability (float, 0.0 to 1.0)\n"
        "- confidence_level (string: 'high', 'medium', or 'low')\n"
        "- forecast_error_buffer (float, 0.0 to 0.5)\n"
        "- uncertainty_range (array of two floats [low, high], 0.0–1.0)\n"
        "- reasoning_summary (short string explanation)\n\n"
        "Do not include any extra keys or text outside the JSON object."
    )


def _build_user_prompt(
    forecast: ForecastData,
    contract: ContractSpec,
    historical_context: Optional[str],
) -> str:
    context_block = historical_context or "No additional historical context provided."
    return (
        "CONTRACT SPECIFICATION:\n"
        f"- Exchange: {contract.exchange}\n"
        f"- Contract ID: {contract.contract_id}\n"
        f"- Station: {contract.station_name} "
        f"({contract.station_lat}, {contract.station_lon})\n"
        f"- Timezone: {contract.timezone}\n"
        f"- Settlement day (local): {contract.settlement_day}\n"
        f"- Settlement rule: {contract.settlement_rule}\n"
        f"- Event definition: {contract.event_definition}\n"
        f"- Threshold F: {contract.threshold_f}\n"
        f"- Comparison: {contract.comparison}\n\n"
        "FORECAST DATA:\n"
        f"- Station name: {forecast.station_name}\n"
        f"- Predicted high F: {forecast.predicted_high_f}\n"
        f"- Predicted low F: {forecast.predicted_low_f}\n"
        f"- Lead hours: {forecast.lead_hours}\n"
        f"- Forecast confidence: {forecast.forecast_confidence}\n"
        f"- Weather condition: {forecast.weather_condition}\n"
        f"- Wind speed mph: {forecast.wind_speed_mph}\n"
        f"- Humidity %: {forecast.humidity_pct}\n"
        f"- Hourly temps F (sample): {forecast.hourly_temps[:12]}\n\n"
        "HISTORICAL CONTEXT (optional):\n"
        f"{context_block}\n\n"
        "TASK:\n"
        "1) Estimate the probability (0.0–1.0) that this contract resolves YES.\n"
        "2) Choose confidence_level based on lead time and forecast quality.\n"
        "3) Choose forecast_error_buffer using these rules:\n"
        "   - 0–12h lead → between 0.03 and 0.05\n"
        "   - 12–24h lead → between 0.05 and 0.08\n"
        "   - 24–48h lead → between 0.08 and 0.12\n"
        "4) Set uncertainty_range as [low, high] capturing a plausible band for the true probability.\n"
        "5) Keep reasoning_summary concise (1–3 sentences).\n\n"
        "Return ONLY the JSON object."
    )


def _parse_json_safely(
    raw_content: str,
    contract: ContractSpec,
    forecast: ForecastData,
) -> ProbabilityEstimate:
    """Parse the model JSON; on failure, return a safe fallback."""
    try:
        payload: Dict[str, Any] = json.loads(raw_content)
    except json.JSONDecodeError:
        # Fallback: 0.5 baseline, buffer from lead hours, 0.4–0.6 range.
        buffer = _buffer_from_lead_hours(forecast.lead_hours)
        return ProbabilityEstimate(
            contract_id=contract.contract_id,
            estimated_probability=0.5,
            confidence_level="medium",
            forecast_error_buffer=buffer,
            uncertainty_range_low=max(0.0, 0.5 - 0.1),
            uncertainty_range_high=min(1.0, 0.5 + 0.1),
            reasoning_summary="Fallback probability due to JSON parse error from OpenAI response.",
            raw_openai_response=raw_content,
        )

    est_prob = float(payload.get("estimated_probability", 0.5))
    est_prob = max(0.0, min(1.0, est_prob))

    confidence = str(payload.get("confidence_level", "medium")).lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "medium"

    buffer = float(payload.get("forecast_error_buffer", _buffer_from_lead_hours(forecast.lead_hours)))
    buffer = max(0.0, min(0.5, buffer))

    unc = payload.get("uncertainty_range", [est_prob - buffer, est_prob + buffer])
    if isinstance(unc, dict):
        low = float(unc.get("low", est_prob - buffer))
        high = float(unc.get("high", est_prob + buffer))
    elif isinstance(unc, (list, tuple)) and len(unc) == 2:
        low = float(unc[0])
        high = float(unc[1])
    else:
        low = est_prob - buffer
        high = est_prob + buffer

    low = max(0.0, min(1.0, low))
    high = max(low, min(1.0, high))

    reasoning_summary = str(payload.get("reasoning_summary", "")).strip() or (
        "No reasoning_summary provided by model."
    )

    return ProbabilityEstimate(
        contract_id=contract.contract_id,
        estimated_probability=est_prob,
        confidence_level=confidence,
        forecast_error_buffer=buffer,
        uncertainty_range_low=low,
        uncertainty_range_high=high,
        reasoning_summary=reasoning_summary,
        raw_openai_response=raw_content,
    )


async def estimate_probability(
    forecast: ForecastData,
    contract: ContractSpec,
    historical_context: Optional[str] = None,
) -> ProbabilityEstimate:
    """Call OpenAI gpt-4o to estimate YES probability for a contract."""
    client = _load_client()

    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(forecast, contract, historical_context)

    try:
        completion = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
    except OpenAIError as exc:  # pragma: no cover - depends on external API
        raise ValueError(f"OpenAI API error while estimating probability: {exc}") from exc

    try:
        raw_content = completion.choices[0].message.content or ""
    except (AttributeError, IndexError) as exc:
        raise ValueError(
            "Unexpected OpenAI response structure while estimating probability."
        ) from exc

    return _parse_json_safely(raw_content, contract, forecast)

