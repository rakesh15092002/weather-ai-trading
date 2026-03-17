"""Uses OpenAI (gpt-4o) to rank trade signals by opportunity score."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List
import json
import os

from dotenv import load_dotenv
from openai import AsyncOpenAI, OpenAIError

from .signal_engine import TradeSignal


MODEL_NAME = "gpt-4o"


@dataclass(frozen=True)
class ScoredOpportunity:
    """A trade signal annotated with an opportunity score and rank."""

    contract_id: str
    action: str
    score: float  # 0.0 to 1.0
    rank: int
    reasoning: str
    original_signal: TradeSignal


def _load_client() -> AsyncOpenAI:
    """Load OpenAI async client using python-dotenv."""
    load_dotenv()
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY is missing. Set it in your environment or .env file."
        )
    return AsyncOpenAI(api_key=api_key)


def _build_system_prompt() -> str:
    return (
        "You are an expert trading opportunity ranker for weather prediction markets. "
        "You will receive a list of candidate trade signals with their metrics, and "
        "you must assign each a score between 0.0 and 1.0 based on expected edge and "
        "confidence.\n\n"
        "Return ONLY a JSON array (no extra text) where each element is an object with "
        "these exact keys:\n"
        "- contract_id (string)\n"
        "- score (float, 0.0 to 1.0)\n"
        "- reasoning (short string explanation)\n"
    )


def _build_user_prompt(signals: List[TradeSignal]) -> str:
    lines = ["CANDIDATE SIGNALS:"]
    for s in signals:
        lines.append(
            f"- contract_id={s.contract_id}, action={s.action}, "
            f"estimated_prob={s.estimated_prob:.3f}, "
            f"market_implied_prob={s.market_implied_prob:.3f}, "
            f"raw_edge={s.raw_edge:.4f}, net_edge={s.net_edge:.4f}, "
            f"confidence={s.confidence}, is_tradeable={s.is_tradeable}"
        )

    lines.append(
        "\nTASK:\n"
        "For each signal, assign a score between 0.0 and 1.0 where higher score means "
        "more attractive opportunity considering:\n"
        "- net_edge (higher is better)\n"
        "- confidence (high > medium > low)\n"
        "- action is not 'no_trade' and is_tradeable should generally get higher scores.\n\n"
        "Respond ONLY with a JSON array. Each array element must be an object with keys:\n"
        "contract_id, score, reasoning.\n"
        "Include an entry for every provided contract_id."
    )

    return "\n".join(lines)


def _fallback_scores(signals: List[TradeSignal]) -> List[ScoredOpportunity]:
    """Deterministic fallback: score directly by net_edge."""
    if not signals:
        return []

    # Normalize net_edge into 0–1 range based on max edge.
    max_edge = max(abs(s.net_edge) for s in signals) or 1.0

    scored: List[ScoredOpportunity] = []
    for s in signals:
        # Only positive net_edge and tradeable get positive scores.
        base = s.net_edge / max_edge if s.net_edge > 0 and s.is_tradeable else 0.0
        score = max(0.0, min(1.0, base))
        scored.append(
            ScoredOpportunity(
                contract_id=s.contract_id,
                action=s.action,
                score=score,
                rank=0,  # placeholder; will be set after sorting
                reasoning="Fallback scoring based on normalized net_edge.",
                original_signal=s,
            )
        )

    scored.sort(key=lambda x: x.score, reverse=True)
    for idx, item in enumerate(scored, start=1):
        object.__setattr__(item, "rank", idx)

    return scored


async def score_opportunities(
    signals: List[TradeSignal],
) -> List[ScoredOpportunity]:
    """Score and rank trade signals by opportunity score using OpenAI."""
    if not signals:
        return []

    if len(signals) == 1:
        # Skip OpenAI; trivial case.
        s = signals[0]
        return [
            ScoredOpportunity(
                contract_id=s.contract_id,
                action=s.action,
                score=1.0,
                rank=1,
                reasoning="Only candidate; assigned score 1.0 by definition.",
                original_signal=s,
            )
        ]

    # Attempt OpenAI ranking; fall back to deterministic scoring on any failure.
    try:
        client = _load_client()
        system_prompt = _build_system_prompt()
        user_prompt = _build_user_prompt(signals)

        completion = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )

        raw_content = completion.choices[0].message.content or "[]"
        # Some models may wrap the array in an object; try to parse flexibly.
        parsed = json.loads(raw_content)
        if isinstance(parsed, dict):
            # Accept {"items": [...]} or similar shapes.
            for candidate_key in ("items", "opportunities", "results"):
                if candidate_key in parsed and isinstance(parsed[candidate_key], list):
                    parsed = parsed[candidate_key]
                    break
        if not isinstance(parsed, list):
            raise ValueError("OpenAI response JSON is not a list.")

        by_id: Dict[str, TradeSignal] = {s.contract_id: s for s in signals}
        scored: List[ScoredOpportunity] = []

        for item in parsed:
            if not isinstance(item, dict):
                continue
            cid = str(item.get("contract_id", "")).strip()
            if not cid or cid not in by_id:
                continue

            signal = by_id[cid]
            try:
                score_val = float(item.get("score", 0.0))
            except (TypeError, ValueError):
                score_val = 0.0
            score_val = max(0.0, min(1.0, score_val))

            reasoning = str(item.get("reasoning", "")).strip() or "No reasoning provided."

            scored.append(
                ScoredOpportunity(
                    contract_id=cid,
                    action=signal.action,
                    score=score_val,
                    rank=0,  # set after sorting
                    reasoning=reasoning,
                    original_signal=signal,
                )
            )

        # Ensure we have at least one scored opportunity; otherwise fall back.
        if not scored:
            return _fallback_scores(signals)

        scored.sort(key=lambda x: x.score, reverse=True)
        for idx, item in enumerate(scored, start=1):
            object.__setattr__(item, "rank", idx)

        return scored

    except (OpenAIError, ValueError, json.JSONDecodeError, KeyError, IndexError):
        # Any failure → deterministic fallback.
        return _fallback_scores(signals)

