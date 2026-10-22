from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, TypedDict

import httpx

from app.config import Settings
from app.errors import LLMUnavailableError


class ChatMessage(TypedDict):
    role: str
    content: str


class LLMClient(Protocol):
    def complete_json(self, messages: Sequence[ChatMessage]) -> str: ...


class OpenAICompatibleClient:
    """Minimal client for any server exposing POST /v1/chat/completions."""

    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.llm_base_url.rstrip("/")
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model
        self.timeout = settings.llm_timeout_seconds
        self.temperature = settings.llm_temperature
        self.max_tokens = settings.llm_max_tokens

    def complete_json(self, messages: Sequence[ChatMessage]) -> str:
        payload = {
            "model": self.model,
            "messages": list(messages),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(f"LLM request failed: {exc}") from exc

        if response.status_code >= 400:
            raise LLMUnavailableError(
                f"LLM returned HTTP {response.status_code}",
                details=response.text[:500],
            )

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMUnavailableError(
                "LLM response did not match the OpenAI chat-completions shape"
            ) from exc

        if not isinstance(content, str) or not content.strip():
            raise LLMUnavailableError("LLM returned an empty response")

        return content
