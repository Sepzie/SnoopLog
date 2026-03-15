"""Ingestion API routes — Person 1 owns this."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from shared.events import bus
from shared.log_buffer import add_to_log_buffer
from shared.models import LogEvent, Tier

logger = logging.getLogger("snooplog.ingestion")

router = APIRouter()


@router.post("/ingest")
async def ingest_json(payload: dict[str, Any] | list[dict[str, Any]]):
    """Accept structured JSON logs. Single object or array."""
    events = payload if isinstance(payload, list) else [payload]
    results = []
    for raw in events:
        event = _process_log(raw)
        results.append({"id": event.id, "score": event.pipeline.anomaly_score})
    return {"accepted": len(results), "results": results}


@router.post("/ingest/raw")
async def ingest_raw(body: str = ""):
    """Accept plain-text logs, one per line."""
    lines = [l for l in body.strip().splitlines() if l.strip()]
    results = []
    for line in lines:
        event = _process_log({"message": line, "raw": line})
        results.append({"id": event.id, "score": event.pipeline.anomaly_score})
    return {"accepted": len(results), "results": results}


def _process_log(raw: dict[str, Any]) -> LogEvent:
    """Parse → filter → score → emit. Returns the scored LogEvent."""
    # TODO (Person 1): plug in parser, pre-filter, ML scorer
    event = LogEvent(
        source=raw.get("source", "unknown"),
        level=raw.get("level", "info"),
        message=raw.get("message", ""),
        raw=raw.get("raw"),
    )

    # Placeholder: heuristic scoring stub
    event.pipeline.anomaly_score = _stub_score(event)
    event.pipeline.tier = _assign_tier(event.pipeline.anomaly_score)

    # Add to shared log buffer (Person 2's search_logs depends on this)
    event_dict = event.model_dump()
    add_to_log_buffer(event_dict)

    # Non-blocking emit — cascade runs in background
    import asyncio
    asyncio.create_task(bus.emit("log:scored", event_dict))

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
