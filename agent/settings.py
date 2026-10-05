"""Agent and API settings, read from environment variables (or the repo's .env).

The LLM endpoint settings (AI_BASE_URL, AI_API_KEY, AI_MODEL) and retrieval
settings live in retrieval/config.py and are reused here, so one .env file
configures the whole service.
"""
from __future__ import annotations

from datetime import date

from retrieval import config as kb  # also loads .env

AI_BASE_URL = kb.AI_BASE_URL
AI_API_KEY = kb.AI_API_KEY
AI_MODEL = kb.AI_MODEL
ABSTAIN_THRESHOLD = kb.ABSTAIN_THRESHOLD

# Optional per-stage model overrides (same endpoint), e.g. a stronger model for drafting.
MODEL_ANALYZE = kb._env("AI_MODEL_ANALYZE", AI_MODEL)
MODEL_ROUTE = kb._env("AI_MODEL_ROUTE", AI_MODEL)
MODEL_GENERATE = kb._env("AI_MODEL_GENERATE", AI_MODEL)
MODEL_JUDGE = kb._env("AI_MODEL_JUDGE", AI_MODEL)
LLM_TIMEOUT = float(kb._env("AI_TIMEOUT", "60"))
LLM_MAX_RETRIES = int(kb._env("AI_MAX_RETRIES", "2"))
# Fallback models (same endpoint), tried in order when the stage's model is overloaded or
# unavailable (HTTP 429 / 5xx), e.g. free tiers under load. Empty = no fallback.
FALLBACK_MODELS = [m.strip() for m in kb._env("AI_MODEL_FALLBACK", "").split(",") if m.strip()]

# How many drafts the generator may produce before the verifier gives up
# (1 = no retry). The plan: retry once, then show the draft marked "unverified".
MAX_DRAFT_ATTEMPTS = int(kb._env("MAX_DRAFT_ATTEMPTS", "2"))
# Second verification layer: an LLM checks that every religious claim is supported
# by the evidence. Off by default for latency; the deterministic layer always runs.
VERIFY_LLM_JUDGE = kb._flag("VERIFY_LLM_JUDGE", False)
# How many recent messages the analyzer and generator see.
CONTEXT_MESSAGES = int(kb._env("CONTEXT_MESSAGES", "8"))

# ---- API access control (the owner's control over the service) -------------------
# Comma-separated keys accepted in the X-API-Key header. Empty = no check (local dev only).
API_KEYS = {k.strip() for k in kb._env("MUEEN_API_KEYS", "").split(",") if k.strip()}
# Last day the service answers (YYYY-MM-DD, inclusive). Empty = no end date.
# Documented and agreed with the team: after this date /suggest returns 403.
_until = kb._env("MUEEN_SERVICE_UNTIL", "")
SERVICE_UNTIL: date | None = date.fromisoformat(_until) if _until else None
# Load the models at startup so the first real request is fast (HANDOFF §2).
WARM_UP = kb._flag("MUEEN_WARM_UP", True)
# Privacy-safe run log (ids, levels, citations, latency — never message text).
RUN_LOG = kb.WORK_DIR / "logs" / "runs.jsonl"
RUN_LOG_ENABLED = kb._flag("MUEEN_RUN_LOG", True)
# Browser origins allowed to call the API directly (normally the site's server calls it).
CORS_ORIGINS = [o.strip() for o in kb._env("MUEEN_CORS_ORIGINS", "").split(",") if o.strip()]
