"""Runs the full end-to-end trading pipeline.

Connects ingestion, probability, signal, risk, execution, and copilot layers.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from ingestion.weather_client import fetch_forecast
from ingestion.market_client import fetch_kalshi_market, fetch_polymarket_market
from ingestion.mapper import (
    get_contract,
    get_city_from_contract,
    list_active_contracts,
)
from ingestion.freshness import (
    FreshnessState,
    update_weather_fetch,
    update_market_fetch,
    is_safe_to_trade,
)
from probability.reasoning_agent import estimate_probability
from probability.calibration import calibrate
from probability.buffer import apply_buffer
from signal.signal_engine import generate_signal
from signal.opportunity_scorer import score_opportunities
from risk.risk_engine import RiskState, check_risk, update_state_on_fill
from risk.position_sizer import calculate_position_size
from execution.execution_engine import place_order
from execution.exit_monitor import check_exit, OpenTrade
from execution.copilot_alerts import generate_anomaly_alert


load_dotenv()


async def run_pipeline(
    contract_ids: Optional[List[str]] = None,
    paper_trading: bool = True,
    entry_threshold: float = 0.04,
) -> List[Dict[str, Any]]:
    """Run the full pipeline for the given contracts and return result dicts."""
    print(f"[{datetime.now(timezone.utc).isoformat()}] Starting pipeline run...")

    if contract_ids is None:
        contract_ids = list_active_contracts()

    results: List[Dict[str, Any]] = []
    freshness_state = FreshnessState()
    risk_state = RiskState()

    for contract_id in contract_ids:
        print(f"--- Processing contract {contract_id} ---")
        result: Dict[str, Any] = {
            "contract_id": contract_id,
            "status": "skipped",
            "action": "no_trade",
            "units": 0,
            "estimated_prob": None,
            "market_prob": None,
            "net_edge": None,
            "reasoning": "",
            "anomaly_alert": None,
            "order_id": None,
        }

        try:
            spec = get_contract(contract_id)
            if spec is None:
                msg = "contract not found in mapper"
                print(f"[WARN] {contract_id}: {msg}")
                result["status"] = "error"
                result["reasoning"] = msg
                results.append(result)
                continue

            # 2. Fetch weather forecast
            print(f"[INFO] {contract_id}: fetching weather forecast...")
            forecast = await fetch_forecast(
                lat=spec.station_lat,
                lon=spec.station_lon,
                timezone=spec.timezone,
                settlement_day=spec.settlement_day,
                api_key="",
            )
            freshness_state = update_weather_fetch(freshness_state)

            # 4. Fetch market data
            print(f"[INFO] {contract_id}: fetching market data...")
            if spec.exchange.lower() == "polymarket":
                market = await fetch_polymarket_market(condition_id=spec.contract_id)
            else:
                market = await fetch_kalshi_market(contract_id=spec.contract_id, api_key="")
            freshness_state = update_market_fetch(freshness_state)

            # 5. Check freshness / safety
            safe, reason = is_safe_to_trade(freshness_state)
            if not safe:
                msg = f"not safe to trade: {reason}"
                print(f"[WARN] {contract_id}: {msg}")
                result["status"] = "skipped"
                result["reasoning"] = msg
                results.append(result)
                continue

            # 6. Estimate probability (OpenAI)
            print(f"[INFO] {contract_id}: estimating probability via OpenAI...")
            prob_estimate = await estimate_probability(
                forecast=forecast,
                contract=spec,
                historical_context=None,
            )

            # 7. Calibrate probability
            calibration = calibrate(prob_estimate, historical_hit_rate=None)

            # 8. Apply buffer
            final_prob = apply_buffer(
                calibration=calibration,
                lead_hours=forecast.lead_hours,
                month=datetime.now(timezone.utc).month,
            )

            # 9. Generate signal
            print(f"[INFO] {contract_id}: generating signal...")
            signal = generate_signal(
                final_prob=final_prob,
                market=market,
                entry_threshold=entry_threshold,
            )

            # 10. Check risk
            city = get_city_from_contract(contract_id)
            print(f"[INFO] {contract_id}: running risk checks for city {city}...")
            decision = check_risk(
                signal=signal,
                market=market,
                city=city,
                state=risk_state,
            )

            if not decision.approved:
                msg = decision.rejection_reason or "risk rejected trade"
                print(f"[WARN] {contract_id}: {msg}")
                result.update(
                    status="rejected",
                    action=signal.action,
                    units=0,
                    estimated_prob=final_prob.final_probability,
                    market_prob=market.yes_price,
                    net_edge=signal.net_edge,
                    reasoning=msg,
                )
                results.append(result)
                continue

            # 11. Calculate position size (override units if needed)
            print(f"[INFO] {contract_id}: calculating position size...")
            pos = calculate_position_size(signal)
            units = min(pos.units, decision.adjusted_units)

            if units <= 0:
                msg = "position size is zero after risk and sizing"
                print(f"[WARN] {contract_id}: {msg}")
                result.update(
                    status="rejected",
                    action=signal.action,
                    units=0,
                    estimated_prob=final_prob.final_probability,
                    market_prob=market.yes_price,
                    net_edge=signal.net_edge,
                    reasoning=msg,
                )
                results.append(result)
                continue

            # 12. Place order
            print(f"[INFO] {contract_id}: placing {'paper' if paper_trading else 'live'} order...")
            # Adjust decision units to the sized amount.
            from risk.risk_engine import RiskDecision  # local import to avoid circular at module load

            sized_decision = RiskDecision(
                approved=True,
                rejection_reason=None,
                adjusted_units=units,
                warnings=decision.warnings,
            )

            order = await place_order(
                signal=signal,
                decision=sized_decision,
                market=market,
                exchange=spec.exchange,
                paper_trading=paper_trading,
            )

            # Update risk state on fill
            risk_state = update_state_on_fill(
                state=risk_state,
                city=city,
                units=units,
                contract_id=contract_id,
            )

            # 13. Generate anomaly alert (copilot)
            print(f"[INFO] {contract_id}: generating anomaly alert...")
            anomaly = await generate_anomaly_alert(
                signal=signal,
                market_spread=market.spread,
                lead_hours=forecast.lead_hours,
            )

            # Optionally run a simple exit check using current price.
            open_trade = OpenTrade(
                contract_id=contract_id,
                action=signal.action,
                units=units,
                entry_price=order.price,
                current_price=order.price,
                entry_time=order.filled_at,
                exchange=spec.exchange,
                order_id=order.order_id,
            )
            _exit_decision = check_exit(trade=open_trade, current_price=order.price)
            # Exit decision is logged, but not acted on in orchestrator.

            result.update(
                status=order.status,
                action=signal.action,
                units=units,
                estimated_prob=final_prob.final_probability,
                market_prob=market.yes_price,
                net_edge=signal.net_edge,
                reasoning="order placed successfully",
                anomaly_alert={
                    "alert_type": anomaly.alert_type,
                    "message": anomaly.message,
                    "severity": anomaly.severity,
                },
                order_id=order.order_id,
            )

        except Exception as exc:
            msg = f"pipeline error: {exc}"
            print(f"[ERROR] {contract_id}: {msg}")
            result["status"] = "error"
            result["reasoning"] = msg

        results.append(result)

    print(f"[{datetime.now(timezone.utc).isoformat()}] Pipeline run complete.")
    return results


async def run_all(paper_trading: bool = True) -> List[Dict[str, Any]]:
    """Run the pipeline for all mapped contracts."""
    return await run_pipeline(contract_ids=None, paper_trading=paper_trading)


async def run_loop(interval_seconds: int = 300, paper_trading: bool = True) -> None:
    """Run the full pipeline in an infinite loop every N seconds."""
    while True:
        try:
            await run_all(paper_trading=paper_trading)
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[FATAL] run_loop encountered error: {exc}")

        print(f"[INFO] Sleeping for {interval_seconds} seconds before next run...")
        await asyncio.sleep(interval_seconds)

