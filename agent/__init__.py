"""Mu'een agent layer (Nader's part).

A LangGraph state machine that turns a da'i's conversation with a seeker into a
draft reply the da'i reviews before sending:

    Analyze -> Route (A-D) -> Retrieve -> Generate -> Verify
                  |              |                      |
                refer         abstain          retry once, then "unverified"

Public entry point:

    from agent import suggest
    result = suggest([{"role": "seeker", "text": "Why do Muslims worship the Kaaba?"}])

Non-negotiable rule (see CLAUDE.md): the model never writes Quran or hadith text.
It writes placeholders such as [[Q:2:144]]; the verifier replaces them with the
exact text from the verbatim store (retrieval.get_verbatim).
"""
from __future__ import annotations

from agent.graph import suggest

__all__ = ["suggest"]
