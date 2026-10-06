# Mu'een (مُعين الداعية)

An AI assistant that drafts source-backed replies for da'is and scholars (callers to Islam)
chatting with people who ask about Islam, integrated into the **Sheykak mobile app**
([sheykak.com](https://sheykak.com)). **The da'i always decides; the assistant proposes.**

## Challenge submission

| | |
|---|---|
| Track | 04 — أدوات المعرفة والتحقق لتمكين المعرفين بالإسلام (knowledge and verification tools) |
| Team | فريق شيخك — فواز الغامدي (knowledge & retrieval), نادر الشهري (agent & API), مهند الدوسري (mobile app), حمزة شاكر (product), عبدالله البطاط (UI/UX) |
| Try it (Android) | APK: [Google Drive](https://drive.google.com/drive/folders/18HbswyfQeVwPXzEpoZTmq6ILZFTm1T1n?usp=sharing). The test accounts are in the presentation (not in this public repo). Sign in as the user and ask a question; sign in as the scholar, accept it from the pending questions, open the chat and tap «استعن بمعين». |
| Live API | `https://mueen.fawazabdullah.dev` (`/health` is public; drafting needs an API key, held only by the app's Supabase Edge Function) |
| Video | [youtu.be/jV01OxZfMTU](https://youtu.be/jV01OxZfMTU) |
| Presentation | Submitted as PDF on the challenge platform |
| App code | The Mu'een module of the app: [MuhannadAldawsari/Sheykak-Mueen](https://github.com/MuhannadAldawsari/sheykak-mueen); the Edge Function is also in [`integration/sheykak/`](integration/sheykak/) |
| Sources | [docs/SOURCES.md](docs/SOURCES.md) — every source, how it is used and verified |

**Starting version (challenge rule on earlier work).** Before the challenge days we prepared the
knowledge layer and a first agent: commits up to `a4c4083` (2026-10-03). Everything after it was
built during the challenge (4–6 Oct 2026): the Shamela books, HadeethEnc hadith, the
independent judge, the reply-language resolver, `/mueen/draft` and the Sheykak app integration,
deployment, and the evaluation in docs/EVALUATION.md §4.1–6. The Sheykak app itself existed
before the challenge; only its Mu'een module was built for it.

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
| **Hybrid search** | `retrieve(queries, lang)` → the 6 most relevant passages from the Quran, the *Bayyinat* Q&A book (263 answered doubts), 33 selected Shamela books (6,766 passages) and HadeethEnc hadith, each with source, reference, link and a 0–1 confidence score used to abstain. |
| **Hadith store** | `get_verbatim("H:hadeethenc:<id>")` → 3,573 hadith graded صحيح / حسن from HadeethEnc (the organiser's encyclopedia) with grade, attribution and approved translations; hadith text is never written by a model. |
| **Misquote detection** | `find_quran_quotes(message)` spots a verse quoted with mistakes and returns the correct reference (challenge test case 11). |
| **Language detection** | `detect_language(text)` → `ar`, `en`, `ur`, `id`, `tl`, … offline. |
| **Glossary** | 84 terms: the challenge's 10 official terms with their usage rules + equivalents from the Jamhara dictionary; `glossary_for()` picks the relevant ones for a prompt. |
| **Evaluation** | Retrieval quality and abstain threshold, misquote detection, and 66 end-to-end safety cases for the agent API (the challenge's 12 + variants). |
| **Dorar (optional)** | Live Dorar hadith search, authentic grades only, **off by default** (dorar.net blocks cloud servers). |

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

The basic build (Quran + Bayyinat) takes a few minutes; Shamela (`--shamela`, ≈45 min) and
HadeethEnc (`--hadith`, ≈1 h the first time) are opt-in. Embeddings are cached in
`data/embeddings/` (committed), so the models do not re-embed the passages. The first run
downloads BGE-M3 (~2.3 GB) from Hugging Face.

With Docker (Qdrant as a server, needed when the API runs several workers):

```bash
docker compose up -d qdrant
docker compose run --rm kb-build
```

## Agent & API (Nader's part — `agent/`, `api/`)

A LangGraph agent behind a FastAPI service, called by the Sheykak app (`POST /mueen/draft`,
through a Supabase Edge Function) and by any site (`POST /suggest`):

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

### Measured results ([docs/EVALUATION.md](docs/EVALUATION.md))

Latest run (§5.2, 65 end-to-end cases incl. the challenge's 12, deployed configuration:
Gemini + independent judge `gpt-5.4-nano`):

| Passing all checks | Level A–D | Level-D referred | Routing | Quran quotes exact | Grounded (common judge) | Mean latency |
|---|---|---|---|---|---|---|
| 64 / 65 (the failure fixed and re-checked) | 100% | 100% | 100% | 100% | 80% | 22.8 s |

Retrieval: Recall@6 98% (held-out 100%), unanswerable questions correctly abstained 100%
(§1, §5, §6). Misquote detection 15 / 15. On the server a draft takes about 30 s.

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
ingest/           build pipeline: download → quran → bayyinat → (shamela, hadith) → build_index (build_all)
data/glossary.json, data/embeddings/   committed data; everything else under data/ is generated
agent/            LangGraph agent: state, nodes, rules, prompts/, templates, llm (model clients)
api/              FastAPI service: /mueen/draft (Sheykak app), /suggest, /suggest/regenerate, /feedback, /stats, /health
integration/      Sheykak app: Supabase Edge Function + integration plan
deploy/           setup/update/stop scripts, Caddy + production compose, Dokploy compose
eval/             retrieval_cases.yaml, safety_cases.yaml, run_eval.py, rejudge.py, results/
docs/             HANDOFF, ARCHITECTURE, AGENT, API_INTEGRATION, DEPLOY, AGENT_WORKLOG,
                  SOURCES, DISCLOSURE, SAFETY, PRIVACY, EVALUATION, DECISIONS
tests/            pytest suite
```

## Documents

* [HANDOFF](docs/HANDOFF.md) — how the agent uses the knowledge layer
* [AGENT](docs/AGENT.md) — the agent pipeline, guarantees and configuration
* [API_INTEGRATION](docs/API_INTEGRATION.md) — for the app and web teams (`/mueen/draft`, `/suggest`)
* [DEPLOY](docs/DEPLOY.md) — server and Dokploy deployment
* [AGENT_WORKLOG](docs/AGENT_WORKLOG.md) — step-by-step log and decisions (Arabic)
* [ARCHITECTURE](docs/ARCHITECTURE.md) — how retrieval works
* [EVALUATION](docs/EVALUATION.md) — measured results and the chosen thresholds
* [SOURCES](docs/SOURCES.md) — every source, version, licence and processing step
* [DISCLOSURE](docs/DISCLOSURE.md) — every tool and model, its role and stage
* [SAFETY](docs/SAFETY.md) · [PRIVACY](docs/PRIVACY.md) · [DECISIONS](docs/DECISIONS.md)

## Licence

Code: MIT (see `LICENSE`). Source texts keep their own terms (see `docs/SOURCES.md`);
the Quran text, translations, the Bayyinat book, the Shamela books and HadeethEnc are
downloaded at build time, not redistributed in this repository.
