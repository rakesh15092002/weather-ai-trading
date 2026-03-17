"""FastAPI application entrypoint.

This module defines the FastAPI app instance and will later include routers
for ingestion, signals, orders, risk, trades, and copilot endpoints.
"""

from __future__ import annotations

from fastapi import FastAPI


app = FastAPI(title="Weather Trading Backend")

