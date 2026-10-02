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


def _api_key(model: str) -> str:
    """OpenCode Zen's free test models (`*-free`) answer without an account key."""
    if settings.AI_API_KEY:
        return settings.AI_API_KEY
    if model.endswith("-free"):
        return "public"
    raise LLMNotConfigured(f"AI_API_KEY is not set and model '{model}' needs one (see .env.example)")


def _default_factory(stage: str):
    from langchain_openai import ChatOpenAI

    model = _MODELS.get(stage, lambda: settings.AI_MODEL)()
    return ChatOpenAI(
        base_url=settings.AI_BASE_URL,
        api_key=_api_key(model),
        model=model,
        temperature=_TEMPERATURE.get(stage, 0.2),
        timeout=settings.LLM_TIMEOUT,
        max_retries=settings.LLM_MAX_RETRIES,
    )


_factory: Callable[[str], Any] = _default_factory


def set_llm_factory(factory: Callable[[str], Any] | None) -> None:
    """Swap the client factory (tests); None restores the real endpoint."""
    global _factory
    _factory = factory or _default_factory


class StructuredOutputError(RuntimeError):
    """The model did not return valid JSON for the schema after all retries."""


def _tool_args(raw: Any) -> dict | None:
    calls = getattr(raw, "tool_calls", None) or []
    return calls[0].get("args") if calls and isinstance(calls[0].get("args"), dict) else None


def _flatten(args: dict, schema: type[BaseModel]) -> dict:
    """Repair a frequent fault of small models: schema fields nested inside another field
    ({"core_question": {"arabic_query": ..., "personal_case": ...}}). Lifts them to the top."""
    fields = set(schema.model_fields)
    out: dict = {}

    def walk(d: dict) -> None:
        for k, v in d.items():
            if isinstance(v, dict) and set(v) & fields:
                walk(v)
            elif k in fields and k not in out:
                out[k] = v
    walk(args)
    return out


def structured(stage: str, schema: type[T], messages: list[tuple[str, str]], retries: int = 2) -> T:
    """Call the stage's model and return a validated `schema` instance.

    Malformed tool calls are repaired when possible (`_flatten`), otherwise the call is
    retried up to `retries` times before StructuredOutputError.
    """
    from pydantic import ValidationError

    bound = _factory(stage).with_structured_output(schema, method="function_calling", include_raw=True)
    last: Exception | None = None
    for _ in range(retries + 1):
        out = bound.invoke(messages)
        if out.get("parsed") is not None:
            return out["parsed"]
        args = _tool_args(out.get("raw"))
        if args:
            try:
                return schema.model_validate(_flatten(args, schema))
            except ValidationError as exc:
                last = exc
        else:
            last = out.get("parsing_error") or RuntimeError("no tool call in the model's answer")
    raise StructuredOutputError(f"{stage}: invalid {schema.__name__} after {retries + 1} tries: {last}")


def text(stage: str, messages: list[tuple[str, str]]) -> str:
    """Plain-text call (used only to translate fixed templates into rare languages)."""
    out = _factory(stage).invoke(messages)
    return getattr(out, "content", str(out)).strip()
