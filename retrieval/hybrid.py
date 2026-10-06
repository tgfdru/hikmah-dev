"""Hybrid retriever: BGE-M3 dense search (Qdrant) + BM25, fused with RRF, then scored.

    from retrieval import retrieve
    retrieve(["why do Muslims face the Kaaba in prayer", "استقبال الكعبة في الصلاة"], lang="en")

Pipeline for each call:
  1. every query -> top-N by dense similarity (Qdrant) and top-N by BM25
  2. Reciprocal Rank Fusion of all those ranked lists
  3. the best RERANK_CANDIDATES are scored 0-1 (reranker or dense cosine, see RERANKER)
  4. per-source diversity (max 2 chunks of the same Bayyinat question), top-k returned

The score is what the agent compares with ABSTAIN_THRESHOLD to decide whether
there is enough evidence to answer at all.
"""
from __future__ import annotations

import atexit
import json
import pickle
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

from retrieval import config
from retrieval.contract import Evidence, SourceType
from retrieval.normalize_ar import strip_diacritics, tokenize
from retrieval.verbatim import get_store

POINT_NS = uuid.UUID("5b0d6f5e-6a64-4bb5-9b0e-2f7a0c1c9e11")
RRF_K = 60
PER_QUERY = 20
MAX_QUERIES = 4
MAX_PER_QUESTION = 2  # passages from the same Bayyinat question or Shamela book


def point_id(logical_id: str) -> str:
    """Stable Qdrant point id for a logical id such as "Q:2:255"."""
    return str(uuid.uuid5(POINT_NS, logical_id))


@lru_cache(maxsize=1)
def qdrant_client():
    from qdrant_client import QdrantClient

    if config.QDRANT_URL:
        return QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY or None, timeout=30)
    config.QDRANT_PATH.mkdir(parents=True, exist_ok=True)
    client = QdrantClient(path=str(config.QDRANT_PATH))
    atexit.register(client.close)  # release the embedded-mode lock before interpreter teardown
    return client


def rrf(rank_lists: list[list[str]], k: int = RRF_K) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion: sum of 1/(k + rank) over every list a doc appears in."""
    scores: dict[str, float] = {}
    for lst in rank_lists:
        for rank, doc_id in enumerate(lst):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


@dataclass
class Candidate:
    id: str
    rrf: float
    dense: float = 0.0  # best cosine similarity to any query
    score: float = 0.0  # final 0-1 confidence
    ranks: dict[str, int] = field(default_factory=dict)


_AR_LETTER = re.compile(r"[\u0621-\u064a]")
_NOT_ARABIC = re.compile(r"[پچژگکیےہۃٹڈڑںھ]")  # Urdu / Persian letters


def _arabic_queries(queries: list[str]) -> set[str]:
    """Queries written in Arabic (by script: fastText calls "ما هو رمضان" Persian)."""
    return {q for q in queries
            if len(_AR_LETTER.findall(q)) >= 3 and not _NOT_ARABIC.search(q)
            and len(_AR_LETTER.findall(q)) > len(re.findall(r"[A-Za-z]", q))}


class HybridRetriever:
    def __init__(self):
        manifest = config.INDEX_DIR / "manifest.json"
        if not manifest.exists():
            raise FileNotFoundError(
                f"{manifest} not found. Build the index with: python -m ingest.build_all"
            )
        self.manifest = json.loads(manifest.read_text(encoding="utf-8"))
        self.docs: dict[str, dict] = {}
        with open(config.INDEX_DIR / "docs.jsonl", encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                self.docs[d["id"]] = d
        with open(config.INDEX_DIR / "bm25.pkl", "rb") as f:
            data = pickle.load(f)
        self.bm25_ids: list[str] = data["ids"]
        self.bm25 = data["bm25"]
        self.bm25_types = np.array([self.docs[i]["type"] for i in self.bm25_ids])
        self.reranker = config.RERANKER
        self._lock = threading.Lock()

    # ---- candidate generation -------------------------------------------------
    def _dense(self, vectors: np.ndarray, types: list[str] | None) -> list[list[tuple[str, float]]]:
        from qdrant_client import models

        flt = None
        if types:
            flt = models.Filter(must=[models.FieldCondition(key="type", match=models.MatchAny(any=types))])
        out = []
        for v in vectors:
            res = qdrant_client().query_points(
                config.QDRANT_COLLECTION, query=v.tolist(), limit=PER_QUERY,
                query_filter=flt, with_payload=["id"],
            ).points
            out.append([(p.payload["id"], float(p.score)) for p in res])
        return out

    def _sparse(self, query: str, types: list[str] | None) -> list[str]:
        tokens = tokenize(query)
        if not tokens:
            return []
        scores = self.bm25.get_scores(tokens)
        if types:
            scores = np.where(np.isin(self.bm25_types, types), scores, 0.0)
        top = np.argsort(-scores)[:PER_QUERY]
        return [self.bm25_ids[i] for i in top if scores[i] > 0]

    def _doc_text(self, doc: dict, limit: int = 1500) -> str:
        if doc["type"] in ("quran", "hadith"):
            return strip_diacritics(doc["text_ar"]) + "\n" + doc.get("translations", {}).get("en", "")
        return strip_diacritics(doc["text_ar"])[:limit]

    def search(self, queries: list[str], types: list[str] | None = None,
               n: int | None = None) -> list[Candidate]:
        """Fused and scored candidates (best first). Used by retrieve() and the eval."""
        from retrieval.models import embed, rerank_scores

        queries = [q.strip() for q in dict.fromkeys(queries) if q and q.strip()][:MAX_QUERIES]
        if not queries:
            return []
        n = n or config.RERANK_CANDIDATES
        qvecs = embed(queries)
        dense_lists = self._dense(qvecs, types)
        sparse_lists = [self._sparse(q, types) for q in queries]
        lists = [[i for i, _ in d] for d in dense_lists] + sparse_lists
        fused = rrf(lists)[: max(n, 1) * 2]

        cands = []
        for doc_id, r in fused:
            c = Candidate(id=doc_id, rrf=r)
            for li, lst in enumerate(lists):
                if doc_id in lst:
                    c.ranks[("dense" if li < len(dense_lists) else "bm25") + str(li % len(queries))] = lst.index(doc_id)
            cands.append(c)
        self._dense_scores(cands, qvecs)
        # Rerankers are expensive: score only the top-n by fused rank. The dense
        # score is free, so in "none" mode every fused candidate is kept.
        if self.reranker != "none":
            cands = cands[:n]

        if self.reranker in ("bge", "minilm"):
            texts = [self._doc_text(self.docs[c.id]) for c in cands]
            scored = queries[: max(1, config.RERANK_QUERIES)]
            arabic = _arabic_queries(scored)
            best = [0.0] * len(cands)
            with self._lock:  # CPU-bound; avoid oversubscription between threads
                for q in scored:
                    for i, s in enumerate(rerank_scores(self.reranker, q, texts)):
                        # Arabic-only passages (Bayyinat, Shamela) are scored against the
                        # Arabic query when there is one: across languages the small
                        # reranker rewards any short definition ("What is Ramadan?" ->
                        # "الروتاري جمعية ..."). Quran records carry English, so all count.
                        if arabic and q not in arabic and self.docs[cands[i].id]["type"] not in ("quran", "hadith"):
                            continue
                        best[i] = max(best[i], s)
            for c, s in zip(cands, best):
                c.score = s
        else:
            for c in cands:
                c.score = c.dense
        cands.sort(key=lambda c: (c.score, c.rrf), reverse=True)
        return cands

    def _dense_scores(self, cands: list[Candidate], qvecs: np.ndarray) -> None:
        """Best cosine similarity of each candidate to any query (BM25-only hits too)."""
        if not cands:
            return
        pts = qdrant_client().retrieve(
            config.QDRANT_COLLECTION, ids=[point_id(c.id) for c in cands], with_vectors=True,
        )
        vecs = {p.id: np.asarray(p.vector, dtype=np.float32) for p in pts}
        for c in cands:
            v = vecs.get(point_id(c.id))
            if v is not None:
                c.dense = float((qvecs @ v).max())

    # ---- public API -------------------------------------------------------------
    def retrieve(self, queries: list[str], lang: str, types: list[SourceType] | None = None,
                 k: int = 6) -> list[Evidence]:
        t0 = time.time()
        wanted = list(types) if types else None
        local_types = list(wanted or ["quran", "qa", "dawah", "hadith"])  # hadith: HadeethEnc, if built
        cands = self.search(queries, local_types or None) if local_types else []

        evidence: list[Evidence] = []
        per_question: dict[str, int] = {}
        for c in cands:
            doc = self.docs[c.id]
            if doc["type"] in ("qa", "dawah"):
                # one Bayyinat question / one Shamela book must not fill every slot
                parent = doc.get("parent_id") or (f"book:{doc['book_id']}" if doc.get("book_id") else doc["id"])
                if per_question.get(parent, 0) >= MAX_PER_QUESTION:
                    continue
                per_question[parent] = per_question.get(parent, 0) + 1
            ev = self._to_evidence(doc, lang, c.score)
            if ev:
                evidence.append(ev)

        if config.DORAR_ENABLED and (wanted is None or "hadith" in wanted):
            from retrieval import dorar

            evidence += dorar.search(queries, lang, scorer=self._score_texts)

        evidence.sort(key=lambda e: e.score, reverse=True)
        self.last_latency_ms = int((time.time() - t0) * 1000)
        return evidence[:k]

    def _score_texts(self, queries: list[str], texts: list[str]) -> list[float]:
        """Score external texts (e.g. Dorar hadith) on the same 0-1 scale as local evidence."""
        from retrieval.models import embed, rerank_scores

        if not texts:
            return []
        if self.reranker in ("bge", "minilm"):
            best = [0.0] * len(texts)
            with self._lock:
                for q in queries[: max(1, config.RERANK_QUERIES)]:
                    best = [max(b, x) for b, x in zip(best, rerank_scores(self.reranker, q, texts))]
            return best
        qv = embed(queries[:MAX_QUERIES])
        tv = embed(texts)
        return [float(x) for x in (tv @ qv.T).max(axis=1)]

    def _to_evidence(self, doc: dict, lang: str, score: float) -> Evidence | None:
        score = round(float(score), 4)
        if doc["type"] in ("quran", "hadith"):
            ev = get_store().get(doc["id"], lang)  # exact text + translation for `lang`
            return ev.model_copy(update={"score": score}) if ev else None
        return Evidence(
            id=doc["id"], type=doc["type"], text_ar=doc["text_ar"],
            translation=(doc.get("translations") or {}).get(lang),
            source=doc["source"], ref=doc["ref"], grade=doc.get("grade"),
            source_url=doc["source_url"], score=score,
        )

    def get_verbatim(self, ref_id: str, lang: str) -> Evidence | None:
        from retrieval.verbatim import get_verbatim

        return get_verbatim(ref_id, lang)


_instance: HybridRetriever | None = None
_instance_lock = threading.Lock()


def get_hybrid() -> HybridRetriever:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = HybridRetriever()
        return _instance
