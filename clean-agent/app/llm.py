"""OpenAI-compatible chat client.

The existing project exposes GPT OSS 120 through an OpenAI-compatible
`/chat/completions` endpoint. This module keeps that integration isolated so
the rest of the agent does not care whether the backend is Ollama, a cloud
gateway, or another compatible server.
"""

from typing import Any

import httpx

from app.config import settings


class LLMResponseError(RuntimeError):
    """Raised when the OpenAI-compatible server returns an unusable response."""


async def chat_completion(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.0,
) -> dict[str, Any]:
    """Send a non-streaming chat completion request to GPT OSS 120."""

    payload: dict[str, Any] = {
        "model": settings.ollama_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 2048,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(f"{settings.ollama_base_url}/chat/completions", json=payload)
        response.raise_for_status()
        try:
            data = response.json()
        except ValueError as exc:
            raise LLMResponseError("LLM response was not valid JSON") from exc

    if not isinstance(data, dict) or not isinstance(data.get("choices"), list) or not data["choices"]:
        raise LLMResponseError("LLM response did not contain a non-empty choices list")
    if not isinstance(data["choices"][0], dict) or not isinstance(data["choices"][0].get("message"), dict):
        raise LLMResponseError("LLM response did not contain a valid message")
    return data
