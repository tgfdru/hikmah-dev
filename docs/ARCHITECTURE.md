# Architecture — knowledge & retrieval layer

```
                 build time (python -m ingest.build_all)                         runtime (imported by the agent)
 ┌────────────────────────────────────────────────────────────┐     ┌──────────────────────────────────────────────┐
 │ Quranpedia dump ──► ingest/quran.py ──► verbatim.sqlite ────┼────►│ get_verbatim("Q:2:255", lang)  exact text     │
 │   (Hafs text, KFC en/ur translations,        │              │     │ match_ayah / find_quran_quotes  misquotes     │
 │    topic labels)                             ▼              │     │                                              │
 │ Bayyinat PDF ──► ingest/pdf_ar.py ──► ingest/bayyinat.py ──►│     │ retrieve(queries, lang, types, k)             │
 │   (ligature repair, verses re-inserted from the store)      │     │   1. BGE-M3 query vectors ──► Qdrant top 20   │
 │                    quran.jsonl + bayyinat.jsonl             │     │   2. BM25 on normalized tokens ──► top 20     │
 │                              │                              │     │   3. Reciprocal Rank Fusion                  │
 │                              ▼                              │     │   4. score 0-1 (dense cosine or reranker)    │
 │           ingest/build_index.py (embedding cache) ──────────┼────►│   5. ≤2 passages per Bayyinat question, top k │
 │              Qdrant collection + bm25.pkl + docs.jsonl      │     │   (+ Dorar hadith if enabled)                 │
 │ Jamhara ──► ingest/glossary.py ──► data/glossary.json ──────┼────►│ glossary_for(texts) / format_for_prompt      │
 │ fastText lid.176 ─────────────────────────────────────────┼────►│ detect_language(text)                        │
 └────────────────────────────────────────────────────────────┘     └──────────────────────────────────────────────┘
```

## Records

Every indexed record becomes an `Evidence` (see `retrieval/contract.py`):

| id | type | text_ar | translation | ref | source_url |
|---|---|---|---|---|---|
| `Q:2:144` | quran | ayah, diacritized | KFC en/ur (None for ar) | `البقرة: 144` | quranpedia.net ayah page |
| `QA:bayyinat:9` | qa | question + similar phrasings + gist + short answer | None | `بينات، السؤال 9` | Bayyinat PDF `#page=65` |
| `QA:bayyinat:9:3` | qa | question title + a ~1,400-char part of the detailed answer | None | `بينات، السؤال 9 (الجواب التفصيلي، الجزء 2)` | PDF `#page=67` |
| `H:bukhari:1` | hadith | as returned by Dorar (optional) | None | `صحيح البخاري - رقم 1` | Dorar search link |

Ranges (`Q:112:1-4`) are assembled on demand from the store with ayah markers.

## What is embedded vs. shown

* Embedded for Quran: Arabic without diacritics + English translation + Quranpedia
  topic labels (so "Kaaba" finds the qibla verses). Only the exact ayah is shown.
* Embedded for Bayyinat: title + passage without diacritics.
* BM25 tokens: normalized Arabic (alef/ya/ta-marbuta unified, light "ال/وال/بال"
  stripping) + English words minus stop words.
* Point ids are `uuid5(logical id)`, so re-indexing one source never overwrites another.

## Scoring and abstaining

`RERANKER` chooses how the 0-1 confidence is computed (see `docs/EVALUATION.md`):

* `minilm` (default) — multilingual MiniLM cross-encoder over the top 12 fused
  candidates, best score against the first 2 queries. Threshold 0.35. ~1.7 s on CPU.
* `none` — best BGE-M3 cosine to any query. No extra model; 0.4 s. Threshold 0.62 (not reliable for abstaining, see EVALUATION).
* `bge` — bge-reranker-v2-m3 (~7.5 s per query on a 4-core CPU; for GPU servers).

The agent abstains when the best score < `ABSTAIN_THRESHOLD` (per-reranker default,
overridable by env).

## Performance (4-core CPU, no GPU)

* First `retrieve()` call: ~25 s (loads BGE-M3). Call once at startup.
* Then: ~1.7 s per call (`minilm`, default) or ~0.4 s (`none`).
* RAM: ~3 GB (BGE-M3) + ~0.5 GB (MiniLM) + ~0.2 GB index.
* Build from scratch without the embedding cache: ~1.5 h on CPU (minutes on a GPU).

## Concurrency and deployment

* Embedded Qdrant (`QDRANT_URL` empty) is single-process. For uvicorn with several
  workers, run the Qdrant server (docker compose) and set `QDRANT_URL`.
* The SQLite store is opened read-only per thread; safe for many workers.
* Models load lazily and once per process.
