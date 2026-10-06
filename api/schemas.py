"""Request/response shapes of the public API (what sheykak.com's server sends and receives).

The response shape matches what eval/run_eval.py expects
(status, level, reply, citations[{id,...}], latency_ms).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Message(BaseModel):
    id: str | None = Field(default=None, max_length=128, description="The site's message id (needed for reply_mode=message)")
    role: Literal["seeker", "dai"] = Field(description="seeker = the person asking; dai = the da'i")
    text: str = Field(min_length=1, max_length=4000)


class SuggestRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=128, description="The site's conversation id (pseudonymous)")
    messages: list[Message] = Field(min_length=1, max_length=50, description="Oldest first")
    reply_mode: Literal["message", "conversation"] = Field(
        default="conversation",
        description="message: the da'i picked a seeker message (target_message_id) — that message is answered and "
                    "decides the reply language; conversation: the latest seeker message is answered")
    target_message_id: str | None = Field(default=None, max_length=128,
                                          description="Required when reply_mode=message: id of the picked seeker message")
    conversation_language: str | None = Field(default=None, max_length=10,
                                              description="Optional fallback only (ISO 639-1), used when no message "
                                                          "has enough text to identify its language")
    seeker_profile_language: str | None = Field(default=None, max_length=10,
                                                description="Optional last fallback (ISO 639-1). Never the app UI "
                                                            "language or the da'i's language")

    @model_validator(mode="after")
    def _target_is_a_seeker_message(self):
        if self.reply_mode == "message":
            if not self.target_message_id:
                raise ValueError("target_message_id is required when reply_mode is 'message'")
            match = [m for m in self.messages if m.id == self.target_message_id]
            if not match:
                raise ValueError("target_message_id is not one of the messages' ids")
            if match[0].role != "seeker":
                raise ValueError("target_message_id must point to a seeker message")
        return self


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
    language_source: str | None = Field(default=None, description="Why that language: target_message | "
                                        "nearby_message | recent_messages | conversation | profile | default")
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
