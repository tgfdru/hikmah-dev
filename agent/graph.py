"""Wires the stages into a LangGraph state machine and exposes `suggest()`.

    analyze -> route --(D)--> refer -> END
                  \\-> retrieve --(no evidence / no hadith)--> abstain -> END
                          |--(level C, no evidence)--> refer (specialist)
                          |--(only a glossary term)--> generate
                          \\-> generate -> verify --(retry)--> generate
                                              \\-> END (ok | unverified)
"""
from __future__ import annotations

import time
import uuid
from functools import lru_cache

from langgraph.graph import END, StateGraph

from agent import nodes
from agent.language import resolve_response_language
from agent.state import AgentState


def _after_route(s: AgentState) -> str:
    return "refer" if s["routing"].level == "D" or s.get("refer_reason") == "judgement" else "retrieve"


def _after_retrieve(s: AgentState) -> str:
    return {"abstain": "abstain", "refer": "refer"}.get(s.get("status") or "", "generate")


def _after_verify(s: AgentState) -> str:
    return "generate" if s.get("verdict") == "retry" else END


def _timed(name: str, fn):
    """Record each stage's wall time (ms) in state["timings"] — summed over retries."""
    def run(state: AgentState) -> dict:
        t0 = time.perf_counter()
        out = fn(state)
        timings = dict(state.get("timings", {}))
        timings[name] = timings.get(name, 0) + int((time.perf_counter() - t0) * 1000)
        return {**out, "timings": timings}
    return run


@lru_cache(maxsize=1)
def build_graph():
    g = StateGraph(AgentState)
    for name in ("analyze", "route", "retrieve", "generate", "verify", "refer", "abstain"):
        g.add_node(name, _timed(name, getattr(nodes, name)))
    g.set_entry_point("analyze")
    g.add_edge("analyze", "route")
    g.add_conditional_edges("route", _after_route, {"refer": "refer", "retrieve": "retrieve"})
    g.add_conditional_edges("retrieve", _after_retrieve,
                            {"abstain": "abstain", "refer": "refer", "generate": "generate"})
    g.add_edge("generate", "verify")
    g.add_conditional_edges("verify", _after_verify, {"generate": "generate", END: END})
    g.add_edge("refer", END)
    g.add_edge("abstain", END)
    return g.compile()


def suggest(messages: list[dict], style: str | None = None, reply_mode: str = "conversation",
            target_message_id: str | None = None, conversation_language: str | None = None,
            profile_language: str | None = None) -> dict:
    """Run the agent on a conversation and return the API-shaped result (see api/schemas.py).

    reply_mode "message": answer the seeker message whose id is `target_message_id`;
    "conversation": answer the latest seeker message. The reply language is decided here, once,
    by agent.language.resolve_response_language — never by the sources' language.
    """
    if not messages:
        raise ValueError("messages must not be empty")
    t0 = time.time()
    decision = resolve_response_language(messages, reply_mode, target_message_id,
                                         conversation_language, profile_language)
    # The agent answers the target message: the context is everything up to and including it,
    # so a later, unrelated message is never mistaken for the question.
    context = messages[:decision.target_index + 1] if decision.target_index >= 0 else messages
    s: AgentState = build_graph().invoke({"messages": context, "style": style, "trace": [],
                                          "language": decision.language,
                                          "language_decision": decision.as_dict()},
                                         config={"recursion_limit": 25})
    a, r = s.get("analysis"), s.get("routing")
    return {
        "suggestion_id": f"s_{uuid.uuid4().hex[:12]}",
        "status": s.get("status", "unverified"),
        "level": r.level if r else None,
        "reply": s.get("final_reply", ""),
        "reply_ar": s.get("final_reply_ar", ""),
        "note_for_dai": s.get("note_for_dai", ""),
        "analysis": {
            "language": s.get("language"),
            "language_source": (s.get("language_decision") or {}).get("source", decision.source),
            "knowledge_level": a.knowledge_level if a else None,
            "tone": a.tone if a else None,
            "core_question": a.core_question if a else None,
            "level_reason": r.reason if r else None,
        },
        "citations": [c.model_dump() for c in s.get("citations", [])],
        "issues": s.get("issues", []),
        "retry_issues": s.get("retry_issues", []),
        "attempts": s.get("attempts", 0),
        "best_score": round(float(s.get("best_score", 0.0) or 0.0), 3),
        "trace": s.get("trace", []),
        "timings_ms": s.get("timings", {}),
        "latency_ms": int((time.time() - t0) * 1000),
    }
