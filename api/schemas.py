"""Request/response shapes of the public API (what sheykak.com's server sends and receives).

The response shape matches what eval/run_eval.py expects
(status, level, reply, citations[{id,...}], latency_ms).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["seeker", "dai"] = Field(description="seeker = the person asking; dai = the da'i")
    text: str = Field(min_length=1, max_length=4000)


class SuggestRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=128, description="The site's conversation id (pseudonymous)")
    messages: list[Message] = Field(min_length=1, max_length=50, description="Oldest first; the last one is answered")


class RegenerateRequest(SuggestRequest):
    style: Literal["simpler", "deeper", "shorter"]


class CitationOut(BaseModel):
    id: str
    type: str
    source: str
    ref: str
    source_url: str
    grade: str | None = None


class AnalysisOut(BaseModel):
    language: str | None = None
    knowledge_level: str | None = None
    tone: str | None = None
    core_question: str | None = None
    level_reason: str | None = None


class SuggestResponse(BaseModel):
    conversation_id: str
    suggestion_id: str
    status: Literal["ok", "refer", "abstain", "unverified"]
    level: Literal["A", "B", "C", "D"] | None
    reply: str = Field(description="Draft in the seeker's language, verse/hadith text inserted from the store")
    reply_ar: str = Field(description="Arabic version for the da'i")
    note_for_dai: str
    analysis: AnalysisOut
    citations: list[CitationOut]
    issues: list[str]
    latency_ms: int
    ai_generated: bool = True
    disclaimer: str = "مسودة مقترحة من مساعد ذكاء اصطناعي — يراجعها الداعية ويعدّلها قبل الإرسال."


class FeedbackRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=128)
    suggestion_id: str = Field(min_length=1, max_length=64)
    action: Literal["sent_as_is", "edited", "rejected"]
    edit_ratio: float | None = Field(default=None, ge=0, le=1, description="Optional: share of the text changed")
