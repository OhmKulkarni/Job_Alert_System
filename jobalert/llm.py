"""Thin client for a local Ollama server, plus a hard budget on LLM calls."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

import requests

from .config import OllamaConfig

log = logging.getLogger("jobalert.llm")


class LLMError(RuntimeError):
    pass


class BudgetExceeded(RuntimeError):
    """The run hit its LLM call ceiling. Remaining work waits for the next run."""


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    raw_arguments: Any = None  # what the model actually sent, for error messages


@dataclass
class ChatResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class ChatModel(Protocol):
    """Anything that can chat. OllamaClient in production, a fake in tests."""

    model: str

    def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        schema: Optional[dict] = None,
    ) -> ChatResponse: ...


class CallBudget:
    def __init__(self, limit: int):
        self.limit = limit
        self.used = 0

    @property
    def remaining(self) -> int:
        return max(self.limit - self.used, 0)

    def spend(self) -> None:
        if self.used >= self.limit:
            raise BudgetExceeded(f"LLM call budget of {self.limit} used up")
        self.used += 1


class BudgetedModel:
    """Wraps a ChatModel so every call is counted against one shared budget."""

    def __init__(self, inner: ChatModel, budget: CallBudget):
        self.inner = inner
        self.budget = budget
        self.model = inner.model

    def chat(self, messages, tools=None, schema=None) -> ChatResponse:
        self.budget.spend()
        return self.inner.chat(messages, tools=tools, schema=schema)


def _parse_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            value = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            return {"__unparseable__": raw}
        return value if isinstance(value, dict) else {"__unparseable__": raw}
    return {}


class OllamaClient:
    def __init__(self, cfg: OllamaConfig, session: Optional[requests.Session] = None):
        self.cfg = cfg
        self.model = cfg.model
        self.session = session or requests.Session()

    def health(self) -> tuple[bool, str]:
        """Check the server is up and the configured model is pulled."""
        try:
            resp = self.session.get(f"{self.cfg.base_url}/api/tags", timeout=5)
            resp.raise_for_status()
        except requests.RequestException as exc:
            return False, f"Ollama is not reachable at {self.cfg.base_url} ({exc.__class__.__name__})"
        names = {m.get("name", "") for m in resp.json().get("models", [])}
        wanted = self.cfg.model if ":" in self.cfg.model else f"{self.cfg.model}:latest"
        if wanted not in names:
            return False, f"Model '{self.cfg.model}' is not pulled. Run: ollama pull {self.cfg.model}"
        return True, "ok"

    def chat(self, messages, tools=None, schema=None) -> ChatResponse:
        payload: dict[str, Any] = {
            "model": self.cfg.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": self.cfg.temperature, "num_ctx": self.cfg.num_ctx},
        }
        if tools:
            payload["tools"] = tools
        if schema:
            payload["format"] = schema  # Ollama structured outputs: constrains decoding to the schema
        try:
            resp = self.session.post(f"{self.cfg.base_url}/api/chat", json=payload, timeout=self.cfg.timeout)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise LLMError(f"Ollama chat failed: {exc}") from exc
        message = resp.json().get("message") or {}
        calls = []
        for call in message.get("tool_calls") or []:
            fn = call.get("function") or {}
            raw = fn.get("arguments")
            calls.append(ToolCall(name=fn.get("name", ""), arguments=_parse_arguments(raw), raw_arguments=raw))
        return ChatResponse(content=message.get("content") or "", tool_calls=calls)
