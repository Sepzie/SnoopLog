"""Ingestion API routes — Person 1 owns this."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Request

from shared.events import bus
from shared.log_buffer import add_to_log_buffer
from shared.models import LogEvent, Tier

from pipeline.ml.model import scorer as ml_scorer

from .filters import apply_filters
from .parser import parse_log
from .scorer import assign_tier, heuristic_score

logger = logging.getLogger("snooplog.ingestion")

router = APIRouter()

# ── Stats counters ─────────────────────────────────────────────────────
_stats = {"total": 0, "filtered": 0, "low": 0, "medium": 0, "high": 0}
_STATS_INTERVAL = 10  # log summary every N events


@router.post("/ingest")
async def ingest_json(payload: dict[str, Any] | list[dict[str, Any]]):
    """Accept structured JSON logs. Single object or array."""
    events = payload if isinstance(payload, list) else [payload]
    results = []
    for raw in events:
        event = _process_log(raw)
        results.append({"id": event.id, "score": event.pipeline.anomaly_score, "filtered": event.pipeline.filtered})
    return {"accepted": len(results), "results": results}


@router.post("/ingest/raw")
async def ingest_raw(request: Request):
    """Accept plain-text logs, one per line."""
    body = (await request.body()).decode("utf-8", errors="replace")
    lines = [line for line in body.strip().splitlines() if line.strip()]
    results = []
    for line in lines:
        event = _process_log(line)
        results.append({"id": event.id, "score": event.pipeline.anomaly_score, "filtered": event.pipeline.filtered})
    return {"accepted": len(results), "results": results}


def _process_log(raw: dict[str, Any] | str) -> LogEvent:
    """Parse → filter → score → emit. Returns the scored LogEvent."""
    # Parse into structured LogEvent
    event = parse_log(raw)

    # Apply pre-filters
    apply_filters(event)

    # Score (skip expensive scoring for filtered logs)
    if not event.pipeline.filtered:
        ml_score = ml_scorer.score(event)
        h_score = heuristic_score(event)
        # Dynamic blend: ML weight ramps from 0% to 40% over first 500 logs
        w = ml_scorer.ml_weight
        event.pipeline.anomaly_score = round(w * ml_score + (1 - w) * h_score, 3)
    else:
        event.pipeline.anomaly_score = 0.0

    event.pipeline.tier = assign_tier(event.pipeline.anomaly_score)

    # Add to shared log buffer (Person 2's search_logs depends on this)
    event_dict = event.model_dump()
    add_to_log_buffer(event_dict)

    # Non-blocking emit — cascade runs in background
    asyncio.create_task(bus.emit("log:scored", event_dict))

    # ── Periodic stats ─────────────────────────────────────────────────
    tier = event.pipeline.tier.value if event.pipeline.tier else "low"
    _stats["total"] += 1
    if event.pipeline.filtered:
        _stats["filtered"] += 1
    _stats[tier] = _stats.get(tier, 0) + 1
    if _stats["total"] % _STATS_INTERVAL == 0:
        logger.info(
            "Pipeline stats — total=%d filtered=%d low=%d medium=%d high=%d ml_weight=%.0f%%",
            _stats["total"], _stats["filtered"],
            _stats.get("low", 0), _stats.get("medium", 0), _stats.get("high", 0),
            ml_scorer.ml_weight * 100,
        )

    return event


def _stub_score(event: LogEvent) -> float:
    """Placeholder heuristic until real ML scorer is wired."""
    level_scores = {"fatal": 0.95, "error": 0.7, "warn": 0.4, "info": 0.1, "debug": 0.05}
    return level_scores.get(event.level.value, 0.2)


def _assign_tier(score: float) -> Tier:
    if score > 0.7:
        return Tier.HIGH
    if score >= 0.3:
        return Tier.MEDIUM
    return Tier.LOW
