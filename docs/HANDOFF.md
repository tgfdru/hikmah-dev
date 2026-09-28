# Handoff: knowledge & retrieval layer → agent (Nader)

This repo contains Fawaz's part of the plan: `ingest/`, `retrieval/`, `data/`,
`eval/`. You build `agent/` and `api/` on top of it. Everything below is what you
need to plug in; nothing here requires changing `retrieval/contract.py`.

## 1. Set up (once)

```bash
python3.11 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # put AI_API_KEY in it
python -m ingest.build_all      # downloads sources, builds store + index (~2 min with the committed cache)
python -m pytest -q             # 30+ tests, should all pass
```

Until the build is done you can work with `RETRIEVER=mock` (no models, no index).

## 2. The two functions from the contract

```python
from retrieval import retrieve, get_verbatim, Evidence

ev: list[Evidence] = retrieve(
    queries=["Why do Muslims worship the Kaaba?", "لماذا يعبد المسلمون الكعبة"],
    lang="en",                 # seeker language (see detect_language below)
    types=None,                # or ["quran"], ["qa"], ["hadith"] ...
    k=6,
)
e = get_verbatim("Q:112:1-4", "en")   # exact Arabic + approved translation, or None
```

* `Evidence.id` formats: `Q:2:255`, `Q:112:1-4`, `QA:bayyinat:9` (the book's question
  + short answer), `QA:bayyinat:9:3` (part of its detailed answer), and — only if the
  Dorar tool is enabled — `H:bukhari:1`, `H:muslim:8`, `H:dorar:<hash>`.
* `Evidence.translation`: the King Fahd Complex translation for `en` / `ur`; `None`
  for Arabic; English for other languages (no approved translation in the store yet).
  Bayyinat passages are Arabic only (`translation=None`); your generator translates
  the *meaning*, never presents it as a quote.
* `Evidence.score` is 0–1. **Abstain when the best score is below
  `retrieval.config.ABSTAIN_THRESHOLD`** (tuned per reranker, see
  `docs/EVALUATION.md`). `retrieve()` does not filter by itself, so you can also show
  "low confidence" evidence to the da'i if you prefer.
* Pass the seeker's own words **and** an Arabic reformulation as `queries` (first two
  are used for scoring): Recall@6 goes from 93% to 98% (docs/EVALUATION.md).
* The first call loads BGE-M3 and the reranker (~15–30 s on CPU). Call
  `retrieve(["warm up"], "en")` at API startup.
* `get_verbatim` is the only source of verse text shown to users. It returns `None`
  for anything unknown (`Q:2:300`, `Q:115:1`, `H:bukhari:999999`, malformed ids) —
  that is your deterministic "hallucinated reference" check.

## 3. Other helpers you will want

```python
from retrieval.langid import detect_language          # ("ur", 0.97) — fastText, offline
from retrieval.ayah_match import match_ayah, find_quran_quotes
from retrieval.verbatim import quran_refs_in
from retrieval.glossary import glossary_for, format_for_prompt
```

| Helper | Use in the agent |
|---|---|
| `detect_language(text)` | Context Analyzer: language of the seeker's last messages (pass them joined). |
| `find_quran_quotes(message)` | Analyzer: detects ayah-like quotes. `m.is_exact == False` ⇒ misquote (challenge case 11). Add `get_verbatim(m.ref_id, lang)` to the evidence so the generator can cite `[[Q:…]]` and the verifier accepts it. |
| `match_ayah(text)` | Same for one snippet. Also useful in the verifier: any Quran-like text the model wrote outside a placeholder ⇒ issue. |
| `quran_refs_in(evidence.text_ar)` | Bayyinat passages quote verses as `﴿…﴾ [البقرة: 144]`. These ids are legitimately part of that evidence, so the verifier can accept `[[Q:2:144]]` when a cited Bayyinat passage contains it. |
| `glossary_for([conversation, *evidence_texts], lang)` + `format_for_prompt(terms, lang)` | Inject only the relevant approved terms into the generation prompt (challenge cases 8 and 12). The 10 official terms carry usage rules. |

## 4. The LLM (OpenAI-compatible endpoint)

We are not using Claude/ALLaM for now. The key is an **OpenCode Zen** key:

```
AI_BASE_URL=https://opencode.ai/zen/v1
AI_API_KEY=...            # env var, never in code
AI_MODEL=space-bunny-free
```

```python
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(base_url=os.environ["AI_BASE_URL"], api_key=os.environ["AI_API_KEY"],
                 model=os.environ["AI_MODEL"], temperature=0.2)
structured = llm.with_structured_output(Analysis, method="function_calling")   # <- important
```

Tested on 2026-09-28:

| Mode | Result with `space-bunny-free` |
|---|---|
| `response_format=json_schema` (LangChain default `json_schema`) | **Ignored** — returned markdown prose |
| `response_format=json_object` | JSON, but the schema is not enforced |
| Forced tool call (`method="function_calling"`) | ✅ Clean JSON matching the schema, ~3 s |

The model also returns `reasoning_content` (thinking) — ignore it. Other models on the
same key (e.g. `claude-sonnet-5`, `gpt-5.4-mini`) can be swapped in via `AI_MODEL`.

## 5. Fixes to the plan's sketches (please apply in your part)

1. `verify.render()` in the plan wraps **every** evidence in Quran brackets `﴿ ﴾`.
   Use `﴿…﴾` only for `type == "quran"`; hadith go in `«…»` with source and grade.
2. The misquoted-ayah case: the verifier only accepts placeholders from retrieved
   evidence, so add the `match_ayah` result to `evidence` (see §3) or it will reject
   the correct verse.
3. The "can I / هل يجوز لي ⇒ Level D" keyword rule misfires on "Can I ask a question?"
   or "Can I learn about Islam?". Require a first-person pronoun **and** a ruling word
   **and** a personal circumstance, or let the LLM router decide with the keyword as a
   hint only.
4. Level D skips retrieval, so its "general information" has no source. Suggest a
   fixed, reviewed referral template plus optional retrieval for general context.
5. Latency: 4 sequential LLM calls + retrieval on CPU will not meet the plan's < 5 s.
   Measured here: retrieval ≈ 1.7 s with the default `RERANKER=minilm` (0.4 s with
   `RERANKER=none`, threshold 0.62); the model ≈ 3 s per call.
6. Privacy: `log_run` in the plan stores full conversations; Level-D questions often
   contain personal details. Keep only the conversation id, levels, ids and metrics, or
   set a retention period (see `docs/PRIVACY.md`).
7. Fake-hadith case: with Dorar off there is no hadith in the store at all, so a
   hadith request should route to `abstain` when `retrieve(..., types=["hadith"])`
   returns nothing — do not fall back to Quran/Bayyinat evidence for it.

## 6. Evaluate your pipeline

```bash
uvicorn api.main:app --port 8000 &
python -m eval.run_eval agent --api http://localhost:8000 --judge
```

Runs the 41 safety cases in `eval/safety_cases.yaml` (the challenge's 12 + variants in
AR/EN/UR/ID) against `POST /suggest` and writes `eval/results/<date>_agent.md` with
level accuracy, refer/abstain routing, citation accuracy, exact-quote check, reply
language, LLM-judge faithfulness and latency. It expects the response shape from the
plan (`status, level, reply, citations[{id,…}], latency_ms`). If you add an API key
header, pass `--api-key` (sent as `X-API-Key`).

## 7. Deploying (sheykak.com)

* The website's **server** calls the API; the key stays on that server (never in the
  browser). A simple `X-API-Key` header check in FastAPI is enough.
* Run Qdrant as a server (`docker compose up -d qdrant`) and set `QDRANT_URL` — the
  embedded on-disk mode allows only one process, so it breaks with several uvicorn workers.
* `docker compose run --rm kb-build` builds the store and index into the `mueen_kb`
  volume; mount that volume in the API container (see `docker-compose.yml`).
* RAM: ~3.5 GB (BGE-M3 + the MiniLM reranker) on CPU; +2.5 GB if `RERANKER=bge`. First start downloads the
  model (~2.3 GB) into `HF_HOME`.
