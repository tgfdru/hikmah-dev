"""Knowledge & retrieval layer for Mu'een.

Public API (see retrieval/contract.py):

    from retrieval import retrieve, get_verbatim, get_retriever, match_ayah

Heavy models (BGE-M3, reranker) load lazily on the first `retrieve` call, so
importing this package is cheap.
"""
from __future__ import annotations

from retrieval.contract import Evidence, Retriever, SourceType
from retrieval.verbatim import get_verbatim

__all__ = [
    "Evidence", "Retriever", "SourceType",
    "get_retriever", "retrieve", "get_verbatim", "match_ayah",
]


def get_retriever() -> Retriever:
    """Return the retriever selected by RETRIEVER (hybrid | mock)."""
    from retrieval import config

    if config.RETRIEVER == "mock":
        from retrieval.mock import MockRetriever

        return MockRetriever()
    from retrieval.hybrid import get_hybrid

    return get_hybrid()


def retrieve(queries: list[str], lang: str, types: list[SourceType] | None = None,
             k: int = 6) -> list[Evidence]:
    return get_retriever().retrieve(queries, lang, types=types, k=k)


def match_ayah(text: str, **kwargs):
    from retrieval.ayah_match import match_ayah as _match

    return _match(text, **kwargs)
