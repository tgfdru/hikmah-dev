# Mu'een (مُعين الداعية) — knowledge & retrieval layer

An AI assistant that drafts source-backed replies for da'is (callers to Islam)
chatting with people who ask about Islam, integrated into
[sheykak.com](https://sheykak.com). **The da'i always decides; the assistant proposes.**

This repository is the **knowledge & retrieval layer** (Fawaz's part of the
[plan](docs/reference/plan.md)). The agent and API (Nader's part) are built on top
of it — start with **[docs/HANDOFF.md](docs/HANDOFF.md)**.

## What it does

| Piece | What it gives the agent |
|---|---|
| **Verbatim Quran store** | `get_verbatim("Q:2:255", "en")` → exact Arabic text (King Fahd Complex print, via Quranpedia) + approved English / Urdu translation. The only source of verse text shown to anyone; unknown ids return `None`. |
| **Hybrid search** | `retrieve(queries, lang)` → the 6 most relevant passages from the Quran and the *Bayyinat* Q&A book (263 answered doubts), each with source, reference, link and a 0–1 confidence score used to abstain. |
| **Misquote detection** | `find_quran_quotes(message)` spots a verse quoted with mistakes and returns the correct reference (challenge test case 11). |
| **Language detection** | `detect_language(text)` → `ar`, `en`, `ur`, `id`, `tl`, … offline. |
| **Glossary** | 84 terms: the challenge's 10 official terms with their usage rules + equivalents from the Jamhara dictionary; `glossary_for()` picks the relevant ones for a prompt. |
| **Evaluation** | Retrieval quality and abstain threshold, misquote detection, and 41 end-to-end safety cases for the agent API (the challenge's 12 + variants). |
| **Hadith (optional)** | Live Dorar search, authentic grades only, **off by default** (untested: dorar.net blocks cloud servers). |

## Quick start

```bash
python3.11 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                 # add AI_API_KEY (only needed for the eval's LLM-judge)
python -m ingest.build_all           # downloads sources, builds store + index
python -m pytest -q
```

```python
from retrieval import retrieve, get_verbatim
for e in retrieve(["Why do Muslims worship the Kaaba?", "لماذا يعبد المسلمون الكعبة"], lang="en"):
    print(f"{e.score:.2f}  {e.id:18}  {e.ref}")
print(get_verbatim("Q:112:1-4", "ur").translation)
```

The build takes about 2 minutes: downloads (~40 MB), Quran store, Bayyinat parsing,
and the index. Embeddings are cached in `data/embeddings/` (committed), so the
models do not have to re-embed ~7,300 passages (≈1.5 h on CPU). The first run
downloads BGE-M3 (~2.3 GB) from Hugging Face.

With Docker (Qdrant as a server, needed when the API runs several workers):

```bash
docker compose up -d qdrant
docker compose run --rm kb-build
```

## Repository layout

```
retrieval/        runtime library (what the agent imports)
  contract.py       Evidence model + retrieve/get_verbatim signatures (shared with the agent)
  verbatim.py       Quran store lookups, ranges, quran_refs_in()
  hybrid.py         BGE-M3 + Qdrant + BM25 + RRF (+ optional reranker)
  ayah_match.py     misquote detection
  langid.py         fastText language id
  glossary.py       glossary selection for prompts
  dorar.py          optional hadith search (off)
  mock.py           RETRIEVER=mock: 3 fixed items, no models
  config.py         all settings (env vars)
ingest/           build pipeline: download → quran → bayyinat → build_index (build_all)
data/glossary.json, data/embeddings/   committed data; everything else under data/ is generated
eval/             retrieval_cases.yaml, safety_cases.yaml, run_eval.py, results/
docs/             HANDOFF, ARCHITECTURE, SOURCES, DISCLOSURE, SAFETY, PRIVACY, EVALUATION, DECISIONS
tests/            pytest suite
```

## Documents

* [HANDOFF](docs/HANDOFF.md) — how the agent uses this layer (start here)
* [ARCHITECTURE](docs/ARCHITECTURE.md) — how retrieval works
* [EVALUATION](docs/EVALUATION.md) — measured results and the chosen thresholds
* [SOURCES](docs/SOURCES.md) — every source, version, licence and processing step
* [DISCLOSURE](docs/DISCLOSURE.md) — every tool and model, its role and stage
* [SAFETY](docs/SAFETY.md) · [PRIVACY](docs/PRIVACY.md) · [DECISIONS](docs/DECISIONS.md)

## Licence

Code: MIT (see `LICENSE`). Source texts keep their own terms (see `docs/SOURCES.md`);
the Quran text, translations and the Bayyinat book are downloaded at build time,
not redistributed in this repository.
