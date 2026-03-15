"""Tier routing for scored log events."""

from __future__ import annotations

import logging
from typing import Any

from pipeline.agent.payloads import build_suppressed_event_payload
from shared.events import bus

logger = logging.getLogger("snooplog.agent.router")


class TierRouter:
    """Routes scored logs to archive, triage, or investigation paths."""

    def __init__(self, batcher, investigator, pattern_memory=None) -> None:
        self._batcher = batcher
        self._investigator = investigator
        self._pattern_memory = pattern_memory

    async def handle(self, event: dict[str, Any]) -> None:
        pipeline_state = event.get("pipeline", {})
        tier = pipeline_state.get("tier", "low")

        if pipeline_state.get("filtered"):
            logger.debug("Skipping filtered log %s", event.get("id"))
            return

        if tier in {"medium", "high"} and self._pattern_memory is not None:
            memory_entry = self._pattern_memory.lookup(event)
            if memory_entry is not None:
                logger.info(
                    "Suppressing previously benign log pattern for %s (seen_count=%s, suppressed_count=%s)",
                    event.get("id"),
                    memory_entry.get("seen_count"),
                    memory_entry.get("suppressed_count"),
                )
                await bus.emit(
                    "log:suppressed",
                    build_suppressed_event_payload(
                        event=event,
                        memory_entry=memory_entry,
                    ),
                )
                return

        if tier == "low":
            await bus.emit("log:archived", event)
            return

        if tier == "medium":
            await self._batcher.add(event)
            return

        await self._investigator.investigate(
            [event],
            reason="high anomaly score",
            urgency="high",
        )
