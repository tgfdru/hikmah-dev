"""Data shapes passed between the agent's stages.

The LLM outputs (Analysis, Routing, Draft, Judgement) are Pydantic models used
with structured output (`method="function_calling"`, HANDOFF §4), so every stage
gets validated JSON, never free text.
"""
from __future__ import annotations

from typing import Literal, TypedDict

from pydantic import BaseModel, Field

from retrieval.contract import Evidence

Level = Literal["A", "B", "C", "D"]
Status = Literal["ok", "refer", "abstain", "unverified"]


class Analysis(BaseModel):
    """Stage 1 — Context Analyzer."""

    language: str = Field(description="ISO 639-1 code of the seeker's language, e.g. en, ar, ur, id, fr")
    knowledge_level: Literal["beginner", "intermediate", "advanced"] = Field(
        description="How much the seeker already knows about Islam")
    background: str = Field(
        description="Seeker's apparent background if stated or obvious (christian, atheist, hindu, muslim, unknown). "
                    "Session-only; never stored.")
    tone: Literal["curious", "skeptical", "hostile"]
    core_question: str = Field(description="The seeker's actual question, restated briefly in Arabic")
    arabic_query: str = Field(
        description="A short Arabic search query for the approved sources (key terms, no quotes of verses)")
    asks_for_hadith: bool = Field(
        description="True if the seeker explicitly asks for a hadith / saying of the Prophet as evidence")
    asks_for_verse: bool = Field(
        default=False, description="True if the seeker asks for the exact text or location of a Quran verse "
                                   "about something specific")
    asked_term: str = Field(default="", description="Arabic form of the term asked about, or empty")
    asks_term_meaning: bool = Field(
        default=False,
        description="True if the seeker asks what an Islamic term means or how to translate it (e.g. Tawhid, Sharia)")
    personal_case: bool = Field(
        description="True if the seeker asks for a ruling on their own specific situation (marriage, money, "
                    "worship validity, family dispute, medical or legal matter)")
    judges_people: bool = Field(default=False, description="True if the seeker asks for a verdict on a specific "
                                "person, sect or group of Muslims (out of scope: referred to scholars)")


class Routing(BaseModel):
    """Stage 2 — Safety Router (levels from the challenge reference pack)."""

    level: Level = Field(description="A settled facts, B explanation/general doubts, C disputed or sensitive, "
                                     "D personal fatwa or individual case")
    reason: str = Field(description="One short sentence explaining the level, in Arabic")


class GroundedPoint(BaseModel):
    """One religious idea the reply conveys — WHAT is said, separate from HOW it is worded."""

    meaning: str = Field(description="The idea in one short plain sentence (English), as the cited evidence "
                                     "establishes it — a summary of its meaning, not a quotation")
    source_ids: list[str] = Field(description="Ids of the evidence or glossary entries that state this idea "
                                              "(Q:..., QA:..., SH:..., GL:..., H:...)")


class Draft(BaseModel):
    """Stage 4 — Draft Generator. `points` fix the content; `reply` only re-expresses them."""

    points: list[GroundedPoint] = Field(default_factory=list, description=(
        "FIRST: the religious points the reply will make (1-5), each tied to the evidence ids that state it. "
        "A religious claim that no evidence states is not a point and must not appear in the reply."))
    reply: str = Field(description="The message to the seeker, in the target language, built only from `points`, "
                                   "in your own conversational words. Quran/hadith only as placeholders [[Q:s:a]]")
    reply_ar: str = Field(description="Arabic translation of the reply for the da'i (same placeholders)")
    cited_ids: list[str] = Field(description="Every evidence id the reply relies on (Q:..., QA:..., SH:..., BK:..., H:...)")
    note_for_dai: str = Field(description="Short note in Arabic for the da'i: approach taken and anything to check")


class Judgement(BaseModel):
    """Stage 5 (optional second layer) — LLM faithfulness check."""

    grounded: bool = Field(description="True if every religious claim in the reply is supported by the evidence")
    contradicts: bool = Field(default=False, description="True if any claim CONTRADICTS the evidence (not merely unsupported)")
    issues: list[str] = Field(default_factory=list, description="Unsupported, overstated or contradicting claims, if any")


class Citation(BaseModel):
    id: str
    type: str
    source: str
    ref: str
    source_url: str
    grade: str | None = None


class AgentState(TypedDict, total=False):
    # input
    messages: list[dict]          # [{"role": "seeker" | "dai", "text": "..."}]
    style: str | None             # regenerate: "simpler" | "deeper" | "shorter"
    audience: str                 # "seeker" (default) | "scholar": who reads the draft first (see graph)
    # stage outputs
    language: str                 # reply language, decided by agent.language before the graph runs
    language_decision: dict       # {"language", "source", "confidence"} — why that language
    analysis: Analysis
    misquotes: list[dict]         # [{"ref_id", "quoted", "similarity"}]
    terms: list[dict]             # approved glossary entries named in the seeker's message
    level_hint: str | None        # deterministic hint for the router (never final)
    routing: Routing
    found: list[Evidence]         # search results gathered while route ran (PARALLEL_RETRIEVE)
    evidence: list[Evidence]
    best_score: float
    abstain_reason: str | None
    refer_reason: str | None      # "personal" (level D) | "specialist" (level C without evidence)
    glossary: dict[str, dict]     # GL id -> glossary entry offered to the generator
    draft: Draft
    attempts: int
    issues: list[str]
    verdict: str                  # verifier: "pass" | "retry" | "fail"
    retry_issues: list[str]       # problems found in rejected drafts (diagnostics)
    # final
    status: Status
    final_reply: str
    final_reply_ar: str
    final_draft: Draft            # the verified draft with its [[Q:..]]/[[H:..]] placeholders
    note_for_dai: str
    citations: list[Citation]
    trace: list[str]              # stage names, for logs and debugging
    timings: dict[str, int]       # ms per stage (summed over retries)
