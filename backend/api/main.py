"""FastAPI application entrypoint.

Creates the app instance, loads environment variables, registers routers,
and configures CORS and a simple health check endpoint.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from .routes.ingest import router as ingest_router
from .routes.signals import router as signals_router
from .routes.orders import router as orders_router
from .routes.risk import router as risk_router
from .routes.trades import router as trades_router
from .routes.copilot import router as copilot_router


load_dotenv()

app = FastAPI(title="Weather Trading Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest_router)
app.include_router(signals_router)
app.include_router(orders_router)
app.include_router(risk_router)
app.include_router(trades_router)
app.include_router(copilot_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Basic health check endpoint."""
    return {"status": "ok"}
