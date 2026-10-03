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
from agent.state import AgentState


def _after_route(s: AgentState) -> str:
    return "refer" if s["routing"].level == "D" else "retrieve"


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


def suggest(messages: list[dict], style: str | None = None) -> dict:
    """Run the agent on a conversation and return the API-shaped result (see api/schemas.py)."""
    if not messages:
        raise ValueError("messages must not be empty")
    t0 = time.time()
    s: AgentState = build_graph().invoke({"messages": messages, "style": style, "trace": []},
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
