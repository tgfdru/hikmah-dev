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


def _endpoint(stage: str) -> tuple[str, str]:
    """(base_url, api_key) for a stage; only the judge can have its own endpoint."""
    if stage == "judge":
        return settings.JUDGE_BASE_URL, settings.JUDGE_API_KEY
    return settings.AI_BASE_URL, settings.AI_API_KEY


def _api_key(model: str, key: str | None = None) -> str:
    """OpenCode Zen's free test models (`*-free`) answer without an account key."""
    key = settings.AI_API_KEY if key is None else key
    if key:
        return key
    if model.endswith("-free"):
        return "public"
    raise LLMNotConfigured(f"AI_API_KEY is not set and model '{model}' needs one (see .env.example)")


def _protocol(model: str, base_url: str | None = None) -> str:
    """Which wire protocol the endpoint expects for this model.

    OpenCode Zen serves GPT models only on /responses and Claude models only on
    /messages (Anthropic format); everything else on /chat/completions. Override with
    AI_PROTOCOL=chat|responses|anthropic for other endpoints.
    """
    if settings.AI_PROTOCOL in ("chat", "responses", "anthropic"):
        return settings.AI_PROTOCOL
    if "opencode.ai/zen" in (base_url or settings.AI_BASE_URL):
        if model.startswith("gpt-"):
            return "responses"
        if model.startswith("claude-"):
            return "anthropic"
    return "chat"


def _client(model: str, stage: str):
    base_url, key = _endpoint(stage)
    common = dict(model=model, timeout=settings.LLM_TIMEOUT, max_retries=settings.LLM_MAX_RETRIES)
    protocol = _protocol(model, base_url)
    if protocol == "anthropic":
        from langchain_anthropic import ChatAnthropic

        # The Anthropic SDK appends /v1/messages itself.
        base = base_url.rstrip("/").removesuffix("/v1")
        return ChatAnthropic(base_url=base, api_key=_api_key(model, key), max_tokens=4096,
                             temperature=_TEMPERATURE.get(stage, 0.2), **common)

    from langchain_openai import ChatOpenAI

    extra = {}
    if protocol == "responses":
        extra["use_responses_api"] = True
        if not model.startswith("gpt-5"):  # GPT-5 reasoning models reject temperature
            extra["temperature"] = _TEMPERATURE.get(stage, 0.2)
    else:
        extra["temperature"] = _TEMPERATURE.get(stage, 0.2)
    return ChatOpenAI(base_url=base_url, api_key=_api_key(model, key), **common, **extra)


def _is_overload(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    return status in (429, 500, 502, 503, 504) or "high demand" in str(exc).lower()


def _default_factory(stage: str):
    """The stage's model, falling back to AI_MODEL_FALLBACK models when it is overloaded."""
    primary = _MODELS.get(stage, lambda: settings.AI_MODEL)()
    fallbacks = settings.FALLBACK_MODELS
    if _endpoint(stage)[0] != settings.AI_BASE_URL:
        fallbacks = []  # fallback models belong to the main endpoint
    models = [primary, *[m for m in fallbacks if m != primary]]
    clients = [_client(m, stage) for m in models]
    if len(clients) == 1:
        return clients[0]
    return _FallbackClient(clients)


class _FallbackClient:
    """Minimal wrapper: same interface as the parts of ChatOpenAI the agent uses."""

    def __init__(self, clients):
        self.clients = clients

    def _run(self, call):
        last = None
        for c in self.clients:
            try:
                return call(c)
            except Exception as exc:  # noqa: BLE001
                if not _is_overload(exc):
                    raise
                last = exc
        raise last

    def invoke(self, messages):
        return self._run(lambda c: c.invoke(messages))

    def with_structured_output(self, schema, **kw):
        outer = self

        class _Bound:
            def invoke(self, messages):
                return outer._run(lambda c: c.with_structured_output(schema, **kw).invoke(messages))
        return _Bound()


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
    content = getattr(out, "text", None)  # AIMessage.text joins content blocks (Responses/Anthropic)
    if not isinstance(content, str):
        content = getattr(out, "content", str(out))
    return content.strip() if isinstance(content, str) else str(content).strip()
