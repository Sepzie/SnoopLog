"""OpenRouter chat client and parsing helpers."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger("snooplog.llm.openrouter")


class OpenRouterError(RuntimeError):
    """Raised when an OpenRouter request fails."""


class OpenRouterChatClient:
    """Minimal async client for OpenRouter chat completions."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        referer: str | None = None,
        title: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self._base_url = base_url or os.getenv(
            "OPENROUTER_BASE_URL",
            "https://openrouter.ai/api/v1/chat/completions",
        )
        self._referer = referer or os.getenv("OPENROUTER_HTTP_REFERER", "https://snooplog.local")
        self._title = title or os.getenv("OPENROUTER_APP_TITLE", "SnoopLog")
        self._timeout_seconds = timeout_seconds

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    async def create_chat_completion(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        response_format: dict[str, Any] | None = None,
        max_tokens: int = 1200,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        if not self._api_key:
            raise OpenRouterError("OPENROUTER_API_KEY is not configured")

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            payload["parallel_tool_calls"] = True
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        if response_format is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": response_format,
            }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self._referer,
            "X-OpenRouter-Title": self._title,
        }

        import httpx

        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(self._base_url, headers=headers, json=payload)

        if response.status_code >= 400:
            raise OpenRouterError(
                f"OpenRouter request failed with {response.status_code}: {response.text}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise OpenRouterError(f"OpenRouter returned invalid JSON: {exc}") from exc


def get_first_message(response: dict[str, Any]) -> dict[str, Any]:
    choices = response.get("choices") or []
    if not choices:
        raise OpenRouterError("OpenRouter response did not include choices")
    message = choices[0].get("message")
    if not message:
        raise OpenRouterError("OpenRouter response did not include a message")
    return message


def get_message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(part.get("text", ""))
        return "\n".join(part for part in text_parts if part)
    return str(content)


def parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        raise ValueError("Empty JSON text")
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        parsed = json.loads(stripped[start : end + 1])
        if isinstance(parsed, dict):
            return parsed

    raise ValueError("Response did not contain a JSON object")
