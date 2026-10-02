"""One place that creates LLM clients, so the model is swappable and disclosed.

All stages use an OpenAI-compatible endpoint (OpenCode Zen by default, HANDOFF §4).
Structured output MUST use `method="function_calling"`: the test model
`space-bunny-free` ignores JSON-schema mode and answers in prose otherwise.

Tests replace the factory with `set_llm_factory()` so the whole graph runs
offline with scripted answers.
"""
from __future__ import annotations

from typing import Any, Callable, TypeVar

from pydantic import BaseModel

from agent import settings

T = TypeVar("T", bound=BaseModel)

_MODELS = {
    "analyze": lambda: settings.MODEL_ANALYZE,
    "route": lambda: settings.MODEL_ROUTE,
    "generate": lambda: settings.MODEL_GENERATE,
    "judge": lambda: settings.MODEL_JUDGE,
    "translate": lambda: settings.MODEL_GENERATE,
}
_TEMPERATURE = {"analyze": 0.0, "route": 0.0, "generate": 0.3, "judge": 0.0, "translate": 0.0}


class LLMNotConfigured(RuntimeError):
    """Raised when AI_API_KEY is missing."""


def _default_factory(stage: str):
    if not settings.AI_API_KEY:
        raise LLMNotConfigured("AI_API_KEY is not set (see .env.example)")
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        base_url=settings.AI_BASE_URL,
        api_key=settings.AI_API_KEY,
        model=_MODELS.get(stage, lambda: settings.AI_MODEL)(),
        temperature=_TEMPERATURE.get(stage, 0.2),
        timeout=settings.LLM_TIMEOUT,
        max_retries=settings.LLM_MAX_RETRIES,
    )


_factory: Callable[[str], Any] = _default_factory


def set_llm_factory(factory: Callable[[str], Any] | None) -> None:
    """Swap the client factory (tests); None restores the real endpoint."""
    global _factory
    _factory = factory or _default_factory


def structured(stage: str, schema: type[T], messages: list[tuple[str, str]]) -> T:
    """Call the stage's model and return a validated `schema` instance."""
    llm = _factory(stage)
    return llm.with_structured_output(schema, method="function_calling").invoke(messages)


def text(stage: str, messages: list[tuple[str, str]]) -> str:
    """Plain-text call (used only to translate fixed templates into rare languages)."""
    out = _factory(stage).invoke(messages)
    return getattr(out, "content", str(out)).strip()
