"""Shared interface between the agent (Nader) and knowledge/retrieval (Fawaz).

This is the contract agreed in the project plan. Do not change a field or a
signature without both owners agreeing (PR required).

    from retrieval import retrieve, get_verbatim

    evidence = retrieve(["why do Muslims face the Kaaba", "القبلة الكعبة"], lang="en")
    ayah = get_verbatim("Q:2:144", lang="en")
"""
from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel

SourceType = Literal["quran", "hadith", "tafsir", "qa", "dawah"]


class Evidence(BaseModel):
    id: str  # "Q:2:255" | "Q:112:1-4" | "H:dorar:<n>" | "QA:bayyinat:41"
    type: SourceType
    text_ar: str  # original Arabic text, with diacritics, exactly as the source
    translation: str | None  # in the seeker's language when available
    source: str  # "القرآن الكريم" | "بينات: أسئلة وأجوبة عن الإسلام" | "صحيح البخاري"
    ref: str  # "البقرة: 255" | "بينات، السؤال 41"
    grade: str | None  # hadith only
    source_url: str
    score: float  # reranker score (0-1); 1.0 for exact lookups


class Retriever(Protocol):
    def retrieve(
        self,
        queries: list[str],
        lang: str,
        types: list[SourceType] | None = None,
        k: int = 6,
    ) -> list[Evidence]: ...

    def get_verbatim(self, ref_id: str, lang: str) -> Evidence | None: ...
