"""API routes for data ingestion (weather + markets)."""

from __future__ import annotations

from fastapi import APIRouter

from ..models.ingest import (
    MarketIngestRequest,
    MarketIngestResponse,
    WeatherIngestRequest,
    WeatherIngestResponse,
)


router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/weather", response_model=WeatherIngestResponse)
async def ingest_weather(payload: WeatherIngestRequest) -> WeatherIngestResponse:
    """Stub endpoint for weather ingestion; business logic wired in later."""
    # TODO: call ingestion.weather_client and mapper here.
    raise NotImplementedError


@router.post("/markets", response_model=MarketIngestResponse)
async def ingest_markets(payload: MarketIngestRequest) -> MarketIngestResponse:
    """Stub endpoint for market ingestion; business logic wired in later."""
    # TODO: call ingestion.market_client here.
    raise NotImplementedError

