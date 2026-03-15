"""Triage clients for medium-tier escalation decisions."""

from __future__ import annotations

import logging
import os
from typing import Any

from pipeline.llm.openrouter import OpenRouterError, get_first_message, get_message_text, parse_json_object
from pipeline.llm.prompts import TRIAGE_SCHEMA, TRIAGE_SYSTEM_PROMPT, build_triage_user_prompt
from shared.models import TriageResult

logger = logging.getLogger("snooplog.llm.triage")


class HeuristicTriageClient:
    """Cheap stand-in for the medium-tier LLM triage step."""

    async def triage(self, logs: list[dict[str, Any]]) -> TriageResult:
        combined = "\n".join(log.get("message", "") for log in logs).lower()

        if any(
            term in combined
            for term in (
                "fatal",
                "traceback",
                "exception",
                "too many connections",
                "connection refused",
                "econnrefused",
                "out of memory",
                "permission denied",
                "unauthorized",
            )
        ):
            return TriageResult(
                escalate=True,
                reason="Detected a repeated or high-impact failure pattern in medium-tier logs.",
                urgency="high",
            )

        warning_count = sum(1 for log in logs if log.get("level") in {"warn", "warning", "error"})
        if warning_count >= 5:
            return TriageResult(
                escalate=True,
                reason="Batch contains enough warning/error logs to justify investigation.",
                urgency="medium",
            )

        return TriageResult(
            escalate=False,
            reason="No clear high-signal failure pattern found in the medium-tier batch.",
            urgency="low",
        )


class OpenRouterTriageClient:
    """OpenRouter-backed triage with heuristic fallback."""

    def __init__(
        self,
        llm_client,
        fallback: HeuristicTriageClient | None = None,
        model: str | None = None,
    ) -> None:
        self._llm_client = llm_client
        self._fallback = fallback or HeuristicTriageClient()
        self._model = model or os.getenv(
            "OPENROUTER_TRIAGE_MODEL",
            "google/gemini-3-flash-preview",
        )

    async def triage(self, logs: list[dict[str, object]]) -> TriageResult:
        if not self._llm_client.enabled:
            return await self._fallback.triage(logs)

        logger.info(
            "Using OpenRouter triage model %s for %s medium-tier log(s)",
            self._model,
            len(logs),
        )
        messages = [
            {"role": "system", "content": TRIAGE_SYSTEM_PROMPT},
            {"role": "user", "content": build_triage_user_prompt(logs)},
        ]

        try:
            response = await self._llm_client.create_chat_completion(
                model=self._model,
                messages=messages,
                response_format=TRIAGE_SCHEMA,
                max_tokens=300,
                temperature=0.0,
            )
            message = get_first_message(response)
            payload = parse_json_object(get_message_text(message))
            return TriageResult.model_validate(payload)
        except (OpenRouterError, ValueError) as exc:
            fallback_result = await self._fallback.triage(logs)
            return fallback_result.model_copy(
                update={"reason": f"Fallback triage used after OpenRouter failure: {exc}"}
            )
