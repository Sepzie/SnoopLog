"""Discord webhook integration for incident notifications."""

from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib import request
from urllib.error import HTTPError, URLError

from shared.config import integration_discord_enabled
logger = logging.getLogger("snooplog.integrations.discord")


class DiscordNotifier:
    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    async def handle_incident(self, data: dict[str, Any]) -> None:
        import asyncio

        payload = build_discord_payload(data)
        try:
            await asyncio.to_thread(post_discord_webhook, self.webhook_url, payload)
        except Exception:
            logger.exception("Discord incident forwarding failed")
            return

        logger.info("Incident forwarded to Discord")


def configure_discord_integration() -> None:
    from shared.events import bus

    if not integration_discord_enabled():
        logger.info("Discord integration disabled in snooplog.yaml; skipping incident subscription")
        return

    webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook_url:
        logger.info("Discord webhook not configured; skipping incident subscription")
        return

    notifier = DiscordNotifier(webhook_url)
    bus.subscribe("incident:created", notifier.handle_incident)
    logger.info("Discord integration subscribed to incident:created")


def build_discord_payload(event: dict[str, Any] | Any) -> dict[str, Any]:
    normalized = _normalize_event(event)
    incident = _extract_incident(normalized)
    metadata = normalized.get("metadata") or {}
    pipeline = normalized.get("pipeline") or {}
    severity = str(incident.get("severity", "medium"))

    summary = _build_summary(normalized, incident)
    code_refs = _format_code_refs(incident.get("code_refs") or [])
    service = metadata.get("service") or normalized.get("source", "unknown")
    tier = pipeline.get("tier") or "unknown"
    model = pipeline.get("tier_model") or "unassigned"

    fields = [
        {
            "name": "Service",
            "value": _truncate(service, 1024),
            "inline": True,
        },
        {
            "name": "Severity",
            "value": f"{_severity_emoji(severity)} {severity.upper()}",
            "inline": True,
        },
        {
            "name": "Anomaly",
            "value": f"{float(pipeline.get('anomaly_score', 0.0)):.2f} ({tier}, {model})",
            "inline": True,
        },
        {
            "name": "Root Cause",
            "value": _truncate(str(incident.get("root_cause") or "No root cause supplied yet."), 1024),
            "inline": False,
        },
        {
            "name": "Suggested Fix",
            "value": _truncate(str(incident.get("suggested_fix") or "Pending investigation."), 1024),
            "inline": False,
        },
        {
            "name": "Code References",
            "value": _truncate(code_refs, 1024),
            "inline": False,
        },
    ]

    metadata_bits = [f"source={normalized.get('source', 'unknown')}"]
    if metadata.get("host"):
        metadata_bits.append(f"host={metadata['host']}")
    if metadata.get("container_id"):
        metadata_bits.append(f"container={metadata['container_id']}")

    return {
        "content": _truncate(
            f"{_severity_emoji(severity)} Incident in `{service}` detected by SnoopLog.",
            2000,
        ),
        "embeds": [
            {
                "title": _truncate(str(incident.get("report") or "SnoopLog Incident"), 256),
                "description": _truncate(summary, 4096),
                "color": _severity_color(severity),
                "fields": fields,
                "footer": {
                    "text": _truncate(" | ".join(metadata_bits), 2048),
                },
                "timestamp": normalized.get("timestamp"),
            }
        ],
    }


def post_discord_webhook(webhook_url: str, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        webhook_url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "SnoopLog-Discord-Test/0.1",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=10.0) as response:
            if response.status >= 400:
                raise RuntimeError(f"Discord webhook returned HTTP {response.status}")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Discord webhook failed with HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Discord webhook request failed: {exc.reason}") from exc


def _normalize_event(event: dict[str, Any] | Any) -> dict[str, Any]:
    if isinstance(event, dict):
        return event
    if hasattr(event, "model_dump"):
        return event.model_dump(mode="json")
    raise TypeError("Expected a dict payload or a model with model_dump().")


def _build_summary(event: dict[str, Any], incident: dict[str, Any]) -> str:
    metadata = event.get("metadata") or {}
    pipeline = event.get("pipeline") or {}
    service = metadata.get("service") or event.get("source", "unknown")
    severity_label = str(incident.get("severity", "medium"))
    score = f"{float(pipeline.get('anomaly_score', 0.0)):.2f}"
    lines = [
        f"{_severity_emoji(severity_label)} {service} is experiencing a {severity_label} incident.",
        f"Signal observed: `{event.get('message', '')}`",
        f"Anomaly score: `{score}` routed through tier `{pipeline.get('tier') or 'unknown'}`.",
    ]

    if incident.get("root_cause"):
        lines.append(f"Root cause summary: {incident['root_cause']}")

    if metadata.get("extra"):
        extra_bits = ", ".join(f"{key}={value}" for key, value in metadata["extra"].items())
        lines.append(f"Relevant metadata: {extra_bits}")

    return "\n".join(lines)


def _extract_incident(event: dict[str, Any]) -> dict[str, Any]:
    incident = event.get("incident")
    if isinstance(incident, dict) and incident:
        return incident

    top_level = {
        "report": event.get("report"),
        "root_cause": event.get("root_cause"),
        "severity": event.get("severity"),
        "suggested_fix": event.get("suggested_fix"),
        "code_refs": event.get("code_refs"),
    }
    if any(value not in (None, "", []) for value in top_level.values()):
        return {
            "report": top_level.get("report") or "SnoopLog incident detected",
            "root_cause": top_level.get("root_cause")
            or "The pipeline flagged an incident but did not provide a detailed root cause yet.",
            "severity": top_level.get("severity") or "medium",
            "suggested_fix": top_level.get("suggested_fix")
            or "Review recent logs and continue the investigation.",
            "code_refs": top_level.get("code_refs") or [],
        }

    return {
        "report": "SnoopLog incident detected",
        "root_cause": "The pipeline flagged an incident but did not provide a detailed root cause yet.",
        "severity": "medium",
        "suggested_fix": "Review recent logs and continue the investigation.",
        "code_refs": [],
    }


def _format_code_refs(code_refs: list[dict[str, Any]]) -> str:
    if not code_refs:
        return "No code references attached yet."

    formatted = []
    for ref in code_refs[:4]:
        location = str(ref.get("file", "unknown"))
        if ref.get("line"):
            location = f"{location}:{ref['line']}"

        details = []
        if ref.get("blame"):
            details.append(f"owner: {ref['blame']}")
        if ref.get("snippet"):
            details.append(f"`{_truncate(str(ref['snippet']), 90)}`")

        suffix = f" ({'; '.join(details)})" if details else ""
        formatted.append(f"- {location}{suffix}")

    return "\n".join(formatted)


def _severity_color(severity: str) -> int:
    colors = {
        "low": 0x57F287,
        "medium": 0xFEE75C,
        "high": 0xFAA61A,
        "critical": 0xED4245,
    }
    return colors.get(severity, colors["medium"])


def _severity_emoji(severity: str) -> str:
    emoji = {
        "low": "🟢",
        "medium": "🟡",
        "high": "🟠",
        "critical": "🔴",
    }
    return emoji.get(severity, "🟡")


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"
