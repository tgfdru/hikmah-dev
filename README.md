# Mu'een (مُعين الداعية)

An AI assistant that drafts source-backed replies for da'is (callers to Islam)
chatting with people who ask about Islam, integrated into
[sheykak.com](https://sheykak.com). **The da'i always decides; the assistant proposes.**

This repository has two layers (see the [plan](docs/reference/plan.md)):

* **Knowledge & retrieval layer** (Fawaz) — `retrieval/`, `ingest/`, `eval/`; start with
  [docs/HANDOFF.md](docs/HANDOFF.md).
* **Agent & API** (Nader) — `agent/`, `api/`, `deploy/`; start with
  [docs/AGENT.md](docs/AGENT.md) and [docs/API_INTEGRATION.md](docs/API_INTEGRATION.md).

No model is fine-tuned: the agent answers by **retrieval-augmented generation** — it drafts
only from passages retrieved from approved sources, and scripture text is always inserted
verbatim from the store, never written by a model.

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

## Agent & API (Nader's part — `agent/`, `api/`)

A LangGraph agent behind a FastAPI service for sheykak.com:

```
analyze → route (A–D) → retrieve → generate → verify ─┬─ ok / unverified
              │              └─ abstain (no source)     └─ retry once
              └─ refer (level D: personal ruling)
```

* **Placeholders, not scripture:** the model writes `[[Q:2:144]]`; the verifier checks the id
  against the evidence and the verbatim store, then inserts the exact text.
* **Two verification layers:** deterministic checks (ids, brackets, verse-like text, level-C
  certainty claims) + an independent LLM judge on its own endpoint. Contradicting the
  evidence blocks the draft; details not in the evidence become review points for the da'i.
* **Human in the loop:** the API only proposes; the da'i edits and sends. Statuses `ok`,
  `unverified`, `refer`, `abstain`.
* **Owner's control:** `X-API-Key` keys, a service end date, a privacy-safe run log (no
  message text), `/stats` and `/feedback`.

### Measured results (41 safety cases incl. the challenge's 12 — [EVALUATION §4](docs/EVALUATION.md))

| Configuration | Pass all checks | Level A–D | Citations valid | Mean latency |
|---|---|---|---|---|
| `space-bunny-free` (run 4) | 36 / 41 | 95% | 100% | 30.3 s |
| Gemini (AI Studio, free tier) | 40 / 41 | 100% | 100% | 32.8 s |
| Gemini + independent judge (**deployed**) | 39 / 41 | 100% | 100% | 29.7 s |

Under one common independent judge (`deepseek-v4.1-flash`), the deployed configuration has
faithfulness 4.32 / 5, 61% of drafts fully grounded, and 1 contradiction with the evidence
(down from 3 without the judge).

### Run locally

```bash
pip install -r requirements-dev.txt          # includes requirements-agent.txt
# .env: see .env.example (Gemini profile, judge endpoint, MUEEN_API_KEYS, MUEEN_SERVICE_UNTIL)
RETRIEVER=mock uvicorn api.main:app --port 8000      # no models needed
uvicorn api.main:app --port 8000                     # after python -m ingest.build_all
python -m eval.run_eval agent --api http://localhost:8000
AI_MODEL=<judge> python -m eval.rejudge eval/results/<run>.json     # common-judge re-score
```

### Deploy

* Own server (Ubuntu 24.04, 8 GB): `deploy/setup.sh` — Docker, Qdrant, knowledge base,
  API, Caddy HTTPS, firewall; `deploy/update.sh`, `deploy/stop.sh`.
* Dokploy: `deploy/docker-compose.dokploy.yml`.
* Details: [docs/DEPLOY.md](docs/DEPLOY.md).

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
agent/            LangGraph agent: state, nodes, rules, prompts/, templates, llm (model clients)
api/              FastAPI service: /suggest, /suggest/regenerate, /feedback, /stats, /health
deploy/           setup/update/stop scripts, Caddy + production compose, Dokploy compose
eval/             retrieval_cases.yaml, safety_cases.yaml, run_eval.py, rejudge.py, results/
docs/             HANDOFF, ARCHITECTURE, AGENT, API_INTEGRATION, DEPLOY, AGENT_WORKLOG,
                  SOURCES, DISCLOSURE, SAFETY, PRIVACY, EVALUATION, DECISIONS
tests/            pytest suite
```

## Documents

* [HANDOFF](docs/HANDOFF.md) — how the agent uses the knowledge layer
* [AGENT](docs/AGENT.md) — the agent pipeline, guarantees and configuration
* [API_INTEGRATION](docs/API_INTEGRATION.md) — for the sheykak.com team
* [DEPLOY](docs/DEPLOY.md) — server and Dokploy deployment
* [AGENT_WORKLOG](docs/AGENT_WORKLOG.md) — step-by-step log and decisions (Arabic)
* [ARCHITECTURE](docs/ARCHITECTURE.md) — how retrieval works
* [EVALUATION](docs/EVALUATION.md) — measured results and the chosen thresholds
* [SOURCES](docs/SOURCES.md) — every source, version, licence and processing step
* [DISCLOSURE](docs/DISCLOSURE.md) — every tool and model, its role and stage
* [SAFETY](docs/SAFETY.md) · [PRIVACY](docs/PRIVACY.md) · [DECISIONS](docs/DECISIONS.md)

## Licence

Code: MIT (see `LICENSE`). Source texts keep their own terms (see `docs/SOURCES.md`);
the Quran text, translations and the Bayyinat book are downloaded at build time,
not redistributed in this repository.
