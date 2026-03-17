"""Fetches OpenWeatherMap hourly forecast using station lat/lon.

This module uses the OpenWeatherMap One Call API 3.0 with an async httpx client.
It filters hourly forecasts for a specific settlement day in the station's
local timezone and returns a structured ForecastData dataclass.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from typing import Any, List

import httpx
from dotenv import load_dotenv
from zoneinfo import ZoneInfo
import os
from statistics import mean


@dataclass(frozen=True)
class ForecastData:
    """Structured weather forecast for a station settlement day."""

    station_name: str
    predicted_high_f: float
    predicted_low_f: float
    hourly_temps: List[float]
    lead_hours: int
    forecast_confidence: str  # high / medium / low
    weather_condition: str
    wind_speed_mph: float
    humidity_pct: float


def _k_to_f(kelvin: float) -> float:
    """Convert temperature from Kelvin to Fahrenheit."""
    return (kelvin - 273.15) * 9.0 / 5.0 + 32.0


def _ms_to_mph(ms: float) -> float:
    """Convert meters per second to miles per hour."""
    return ms * 2.2369362920544


def _confidence_from_lead_hours(lead_hours: int) -> str:
    """Map lead time (in hours) to qualitative confidence."""
    if lead_hours < 0:
        lead_hours = 0

    if 0 <= lead_hours <= 12:
        return "high"
    if 12 < lead_hours <= 24:
        return "medium"
    if 24 < lead_hours <= 48:
        return "low"

    raise ValueError(
        f"lead_hours={lead_hours} exceeds 48 hours; refusing to generate forecast for such long lead time."
    )


async def fetch_forecast(
    lat: float,
    lon: float,
    timezone: str,
    settlement_day: str,
    api_key: str,
) -> ForecastData:
    """Fetch and summarize hourly forecast for a given settlement day.

    Args:
        lat: Station latitude.
        lon: Station longitude.
        timezone: IANA timezone string (e.g. 'America/New_York').
        settlement_day: Target local calendar day as 'YYYY-MM-DD'.
        api_key: Optional explicit OpenWeatherMap API key. If empty, falls
            back to OPENWEATHER_API_KEY from environment (.env via python-dotenv).

    Returns:
        ForecastData for the specified settlement day.

    Raises:
        ValueError: For invalid inputs, missing data, or unsupported lead times.
        httpx.HTTPError: If the HTTP request fails.
    """
    load_dotenv()

    key = (api_key or "").strip() or (os.getenv("OPENWEATHER_API_KEY") or "").strip()
    if not key:
        raise ValueError(
            "OpenWeather API key is missing. Provide `api_key` argument or set OPENWEATHER_API_KEY in environment."
        )

    try:
        tz = ZoneInfo(timezone)
    except Exception as exc:  # pragma: no cover - depends on OS tzdata
        raise ValueError(
            f"Invalid timezone '{timezone}'. Expected a valid IANA timezone like 'America/New_York'."
        ) from exc

    try:
        settle_date: date = date.fromisoformat(settlement_day)
    except Exception as exc:
        raise ValueError(
            f"Invalid settlement_day '{settlement_day}'. Expected ISO format 'YYYY-MM-DD'."
        ) from exc

    # Settlement-day window in local time
    start_local = datetime.combine(settle_date, time(0, 0), tzinfo=tz)
    end_local = start_local + timedelta(days=1)

    # Compute lead_hours from *now* until the start of the settlement day in local time
    now_utc = datetime.now(dt_timezone.utc)
    now_local = now_utc.astimezone(tz)
    lead_delta = start_local - now_local
    lead_hours = int(lead_delta.total_seconds() // 3600)
    if lead_hours < 0:
        # Already in or past the settlement day; treat as 0-hour lead
        lead_hours = 0

    # Validate lead time against rules
    confidence = _confidence_from_lead_hours(lead_hours)

    url = "https://api.openweathermap.org/data/3.0/onecall"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": key,
        # Keep Kelvin (default) so we explicitly satisfy "convert Kelvin to Fahrenheit"
        "exclude": "current,minutely,daily,alerts",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text
            raise ValueError(
                f"OpenWeather API returned HTTP {exc.response.status_code}: {detail}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ValueError(f"Failed to reach OpenWeather API: {exc}") from exc

    data: dict[str, Any] = response.json()
    hourly = data.get("hourly")
    if not isinstance(hourly, list):
        raise ValueError("OpenWeather response missing 'hourly' forecast data.")

    temps_f: list[float] = []
    conditions: list[str] = []
    winds_mph: list[float] = []
    humidities: list[float] = []

    for hour in hourly:
        ts_unix = hour.get("dt")
        if ts_unix is None:
            continue

        # Hour timestamp is in UTC; convert to station local time
        ts_utc = datetime.fromtimestamp(int(ts_unix), tz=dt_timezone.utc)
        ts_local = ts_utc.astimezone(tz)

        if not (start_local <= ts_local < end_local):
            continue

        temp_k = hour.get("temp")
        if temp_k is None:
            continue
        temps_f.append(_k_to_f(float(temp_k)))

        weather_arr = hour.get("weather") or []
        if weather_arr and isinstance(weather_arr, list):
            desc = weather_arr[0].get("description") or weather_arr[0].get("main") or "unknown"
            conditions.append(str(desc))

        wind_ms = hour.get("wind_speed")
        if wind_ms is not None:
            winds_mph.append(_ms_to_mph(float(wind_ms)))

        humidity_val = hour.get("humidity")
        if humidity_val is not None:
            humidities.append(float(humidity_val))

    if not temps_f:
        raise ValueError(
            f"No hourly forecast data found for settlement_day={settlement_day} at lat={lat}, lon={lon}."
        )

    predicted_high_f = max(temps_f)
    predicted_low_f = min(temps_f)

    # Derive summary condition as the most frequent description, or fallback
    if conditions:
        condition_counts: dict[str, int] = {}
        for c in conditions:
            condition_counts[c] = condition_counts.get(c, 0) + 1
        weather_condition = max(condition_counts.items(), key=lambda kv: kv[1])[0]
    else:
        weather_condition = "unknown"

    wind_speed_mph = mean(winds_mph) if winds_mph else 0.0
    humidity_pct = mean(humidities) if humidities else 0.0

    station_name = f"lat={lat:.4f},lon={lon:.4f}"

    return ForecastData(
        station_name=station_name,
        predicted_high_f=predicted_high_f,
        predicted_low_f=predicted_low_f,
        hourly_temps=temps_f,
        lead_hours=lead_hours,
        forecast_confidence=confidence,
        weather_condition=weather_condition,
        wind_speed_mph=wind_speed_mph,
        humidity_pct=humidity_pct,
    )

