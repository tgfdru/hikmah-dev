"""FastAPI service for the Mu'een agent.

Endpoints (all JSON; all but /health need the X-API-Key header when MUEEN_API_KEYS is set):
  GET  /health                service + knowledge-layer status (no key needed)
  POST /suggest               draft a reply for the latest seeker message
  POST /suggest/regenerate    same, with style = simpler | deeper | shorter
  POST /feedback              what the da'i did with a draft (sent as is / edited / rejected)
  GET  /stats                 acceptance rate and level/status counts from the run log

Access control is the service owner's: keys in MUEEN_API_KEYS, and an optional end
date MUEEN_SERVICE_UNTIL after which the service answers 403 (documented in
docs/API_INTEGRATION.md and agreed with the team).

Privacy (docs/PRIVACY.md): the run log keeps ids, levels, statuses, cited ids and
latency only — never message text.
"""
from __future__ import annotations

import json
import logging
import secrets
import threading
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from agent import settings
from agent.graph import suggest as run_agent
from agent.llm import LLMNotConfigured
from api.schemas import FeedbackRequest, RegenerateRequest, SuggestRequest, SuggestResponse
from retrieval import config as kb

log = logging.getLogger("mueen.api")
_log_lock = threading.Lock()
_state = {"warm": False, "warm_error": None}


def _warm_up() -> None:
    """Load BGE-M3 + reranker once at startup (first call takes 15-30 s, HANDOFF §2)."""
    if not settings.WARM_UP or kb.RETRIEVER == "mock":
        _state["warm"] = True
        return
    try:
        from retrieval import retrieve

        retrieve(["warm up"], "en")
        _state["warm"] = True
    except Exception as exc:  # the API still starts; /health reports the problem
        _state["warm_error"] = str(exc)
        log.error("warm-up failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=_warm_up, daemon=True).start()
    yield


app = FastAPI(title="Mu'een AI — da'i reply assistant", version="1.0.0", lifespan=lifespan,
              description="Drafts source-backed replies for da'is. The da'i always reviews before sending.")
if settings.CORS_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS,
                       allow_methods=["GET", "POST"], allow_headers=["X-API-Key", "Content-Type"])


# ------------------------------------------------------------------ access ---
def require_access(x_api_key: str | None = Header(default=None)) -> None:
    if settings.SERVICE_UNTIL and date.today() > settings.SERVICE_UNTIL:
        raise HTTPException(403, detail=f"Service period ended on {settings.SERVICE_UNTIL.isoformat()}. "
                                        "Contact the service owner.")
    if not settings.API_KEYS:
        return  # local development only — set MUEEN_API_KEYS in any shared deployment
    if not x_api_key or not any(secrets.compare_digest(x_api_key, k) for k in settings.API_KEYS):
        raise HTTPException(401, detail="Missing or invalid X-API-Key")


# --------------------------------------------------------------------- log ---
def _append_log(record: dict) -> None:
    if not settings.RUN_LOG_ENABLED:
        return
    record = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **record}
    try:
        settings.RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _log_lock, settings.RUN_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        log.warning("run log not written: %s", exc)


# ---------------------------------------------------------------- handlers ---
@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "retriever": kb.RETRIEVER,
        "models_loaded": _state["warm"],
        "warm_up_error": _state["warm_error"],
        "verbatim_store": kb.VERBATIM_DB.exists(),
        "llm_configured": bool(settings.AI_API_KEY),
        "llm_model": settings.AI_MODEL,
        "abstain_threshold": settings.ABSTAIN_THRESHOLD,
        "service_until": settings.SERVICE_UNTIL.isoformat() if settings.SERVICE_UNTIL else None,
        "auth_required": bool(settings.API_KEYS),
    }


def _run(req: SuggestRequest, style: str | None) -> SuggestResponse:
    messages = [m.model_dump() for m in req.messages]
    try:
        out = run_agent(messages, style=style)
    except LLMNotConfigured as exc:
        raise HTTPException(503, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("agent failed for %s", req.conversation_id)
        raise HTTPException(502, detail="The assistant could not produce a draft. Please try again.") from exc
    _append_log({
        "event": "suggest", "conversation_id": req.conversation_id, "suggestion_id": out["suggestion_id"],
        "style": style, "status": out["status"], "level": out["level"],
        "language": out["analysis"].get("language"), "cited": [c["id"] for c in out["citations"]],
        "issues": len(out["issues"]), "attempts": out["attempts"], "best_score": out["best_score"],
        "latency_ms": out["latency_ms"], "trace": out["trace"],
    })
    return SuggestResponse(conversation_id=req.conversation_id, **{
        k: out[k] for k in ("suggestion_id", "status", "level", "reply", "reply_ar", "note_for_dai",
                            "analysis", "citations", "issues", "latency_ms")})


@app.post("/suggest", response_model=SuggestResponse, dependencies=[Depends(require_access)])
def suggest(req: SuggestRequest) -> SuggestResponse:
    return _run(req, None)


@app.post("/suggest/regenerate", response_model=SuggestResponse, dependencies=[Depends(require_access)])
def regenerate(req: RegenerateRequest) -> SuggestResponse:
    return _run(req, req.style)


@app.post("/feedback", dependencies=[Depends(require_access)])
def feedback(req: FeedbackRequest) -> dict:
    _append_log({"event": "feedback", **req.model_dump()})
    return {"saved": True}


@app.get("/stats", dependencies=[Depends(require_access)])
def stats() -> dict:
    """Counts from the run log: the plan's "accepted without major edit" metric."""
    counts: dict = {"suggest": 0, "status": {}, "level": {}, "feedback": {}}
    latencies: list[int] = []
    if settings.RUN_LOG.exists():
        for line in settings.RUN_LOG.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("event") == "suggest":
                counts["suggest"] += 1
                counts["status"][r["status"]] = counts["status"].get(r["status"], 0) + 1
                lvl = r.get("level") or "-"
                counts["level"][lvl] = counts["level"].get(lvl, 0) + 1
                latencies.append(int(r.get("latency_ms", 0)))
            elif r.get("event") == "feedback":
                counts["feedback"][r["action"]] = counts["feedback"].get(r["action"], 0) + 1
    fb = sum(counts["feedback"].values())
    counts["accepted_as_is_rate"] = round(counts["feedback"].get("sent_as_is", 0) / fb, 3) if fb else None
    counts["median_latency_ms"] = sorted(latencies)[len(latencies) // 2] if latencies else None
    return counts
