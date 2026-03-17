"""AI copilot alerts: anomaly summaries and post-trade analysis.

This module is *advisory only*:
- Uses OpenAI gpt-4o to generate text insights
- Never changes or decides trades
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
import json
import os

from dotenv import load_dotenv
from openai import AsyncOpenAI, OpenAIError

from signal.signal_engine import TradeSignal
from .execution_engine import OrderResult


MODEL_NAME = "gpt-4o"


@dataclass(frozen=True)
class AnomalyAlert:
    """LLM-generated anomaly or warning about a potential risk."""

    contract_id: str
    alert_type: str  # anomaly / warning / info
    message: str
    suggested_action: str
    severity: str  # high / medium / low


@dataclass(frozen=True)
class PostTradeAnalysis:
    """LLM-generated reflection on a completed trade."""

    contract_id: str
    outcome: str
    pnl_pct: float
    analysis: str
    lessons: str


def _load_client() -> AsyncOpenAI:
    """Load OpenAI async client using python-dotenv."""
    load_dotenv()
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY is missing. Set it in your environment or .env file."
        )
    return AsyncOpenAI(api_key=api_key)


async def generate_anomaly_alert(
    signal: TradeSignal,
    market_spread: float,
    lead_hours: int,
) -> AnomalyAlert:
    """Ask OpenAI to highlight any risk/anomaly conditions for a signal."""
    client = _load_client()

    system_prompt = (
        "You are a trading risk monitor and analyst for weather prediction markets. "
        "You NEVER decide or change trades; you only surface anomalies and warnings.\n\n"
        "Return ONLY a single JSON object with these exact keys:\n"
        "- alert_type (one of: 'anomaly', 'warning', 'info')\n"
        "- message (short human-readable summary)\n"
        "- suggested_action (short advice, e.g., 'reduce size', 'monitor closely')\n"
        "- severity (one of: 'high', 'medium', 'low')\n"
    )

    user_prompt = (
        "Evaluate the following candidate trade purely for anomalies and risk flags.\n\n"
        f"CONTRACT ID: {signal.contract_id}\n"
        f"ACTION: {signal.action}\n"
        f"ESTIMATED_PROB: {signal.estimated_prob}\n"
        f"MARKET_IMPLIED_PROB: {signal.market_implied_prob}\n"
        f"RAW_EDGE: {signal.raw_edge}\n"
        f"NET_EDGE: {signal.net_edge}\n"
        f"CONFIDENCE: {signal.confidence}\n"
        f"POSITION_UNITS: {signal.position_units}\n"
        f"MARKET_SPREAD: {market_spread}\n"
        f"LEAD_HOURS: {lead_hours}\n\n"
        "Focus on:\n"
        "- unusually wide bid/ask spread\n"
        "- very long lead time but strong conviction\n"
        "- low confidence but large size\n"
        "- suspicious or inconsistent pricing vs probability\n\n"
        "Do NOT recommend specific trades. Only flag anomalies and suggest generic actions.\n"
        "Return ONLY the JSON object."
    )

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
        raw_content = completion.choices[0].message.content or ""
    except OpenAIError as exc:  # pragma: no cover - external API
        # Fallback: simple local anomaly logic.
        severity = "low"
        alert_type = "info"
        message = "AI anomaly detection unavailable; using deterministic fallback."
        suggested_action = "monitor manually"

        if market_spread > 0.08 or lead_hours > 48:
            severity = "medium"
            alert_type = "warning"
            message = "Wide market spread or long lead time detected."
            suggested_action = "review trade size and risk limits"

        return AnomalyAlert(
            contract_id=signal.contract_id,
            alert_type=alert_type,
            message=message,
            suggested_action=suggested_action,
            severity=severity,
        )

    # Parse JSON safely with fallback.
    try:
        payload: Dict[str, Any] = json.loads(raw_content)
        alert_type = str(payload.get("alert_type", "info")).lower()
        if alert_type not in {"anomaly", "warning", "info"}:
            alert_type = "info"

        severity = str(payload.get("severity", "low")).lower()
        if severity not in {"high", "medium", "low"}:
            severity = "low"

        message = str(payload.get("message", "")).strip() or "No message provided."
        suggested_action = (
            str(payload.get("suggested_action", "")).strip()
            or "No specific action suggested."
        )

    except json.JSONDecodeError:
        # Fallback heuristic if JSON is malformed.
        alert_type = "info"
        severity = "low"
        message = "Malformed anomaly JSON from OpenAI; treating as informational."
        suggested_action = "monitor manually; consider adding logging for this contract."

    return AnomalyAlert(
        contract_id=signal.contract_id,
        alert_type=alert_type,
        message=message,
        suggested_action=suggested_action,
        severity=severity,
    )


async def generate_post_trade_analysis(
    order: OrderResult,
    outcome: str,
    pnl_pct: float,
    actual_temp_f: Optional[float] = None,
) -> PostTradeAnalysis:
    """Ask OpenAI for a short, human-readable post-trade analysis."""
    client = _load_client()

    system_prompt = (
        "You are a trading risk monitor and analyst. "
        "You NEVER decide or change trades; you only explain what happened and "
        "surface lessons learned.\n\n"
        "Return ONLY a single JSON object with these exact keys:\n"
        "- analysis (short explanation of why the trade outcome occurred)\n"
        "- lessons (short bullet-style or sentence-style lessons)\n"
    )

    user_prompt = (
        "Provide a concise post-trade analysis for the following trade.\n\n"
        f"CONTRACT ID: {order.contract_id}\n"
        f"ACTION: {order.action}\n"
        f"UNITS: {order.units}\n"
        f"PRICE_FILLED: {order.price}\n"
        f"EXCHANGE: {order.exchange}\n"
        f"ORDER_STATUS: {order.status}\n"
        f"OUTCOME: {outcome}\n"
        f"PNL_PCT: {pnl_pct}\n"
        f"FILLED_AT: {order.filled_at.isoformat()}\n"
    )

    if actual_temp_f is not None:
        user_prompt += f"ACTUAL_TEMP_F: {actual_temp_f}\n"

    user_prompt += (
        "\nFocus on:\n"
        "- what the implied forecast was vs the actual realization\n"
        "- whether sizing and risk were appropriate\n"
        "- any systematic bias (e.g., consistently overestimating heat events)\n"
        "- clear, actionable lessons for future trades\n\n"
        "Do NOT give new trade recommendations. Only analyze and reflect.\n"
        "Return ONLY the JSON object."
    )

    try:
        completion = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        raw_content = completion.choices[0].message.content or ""
    except OpenAIError as exc:  # pragma: no cover - external API
        # Fallback: deterministic explanation.
        base_analysis = (
            f"Post-trade analysis unavailable due to OpenAI error: {exc}. "
            "Using deterministic fallback summary based on PnL only."
        )
        if pnl_pct >= 0:
            lessons = "Winning trade; review whether edge signal was strong or if sizing could be improved."
        else:
            lessons = (
                "Losing trade; review forecast assumptions, market conditions, and risk limits "
                "to avoid similar drawdowns."
            )
        return PostTradeAnalysis(
            contract_id=order.contract_id,
            outcome=outcome,
            pnl_pct=pnl_pct,
            analysis=base_analysis,
            lessons=lessons,
        )

    try:
        payload: Dict[str, Any] = json.loads(raw_content)
    except json.JSONDecodeError:
        # Fallback if JSON is malformed.
        if pnl_pct >= 0:
            analysis = "Trade outcome was positive; JSON parse error prevents deeper AI analysis."
            lessons = "Consolidate what worked in this setup and monitor for overconfidence."
        else:
            analysis = "Trade outcome was negative; JSON parse error prevents deeper AI analysis."
            lessons = "Revisit model calibration and risk controls for similar events."
        return PostTradeAnalysis(
            contract_id=order.contract_id,
            outcome=outcome,
            pnl_pct=pnl_pct,
            analysis=analysis,
            lessons=lessons,
        )

    analysis = str(payload.get("analysis", "")).strip() or (
        "No analysis provided by model."
    )
    lessons = str(payload.get("lessons", "")).strip() or (
        "No lessons provided by model."
    )

    return PostTradeAnalysis(
        contract_id=order.contract_id,
        outcome=outcome,
        pnl_pct=pnl_pct,
        analysis=analysis,
        lessons=lessons,
    )

