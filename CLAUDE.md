# Mu'een — repository guide for AI coding agents

Knowledge & retrieval layer of an assistant that drafts source-backed replies for
da'is, plus the agent/API layer (`agent/`, `api/`, owned by Nader — see docs/AGENT.md).

## Non-negotiable rules

* Never write, paraphrase or "fix" Quran text or hadith in code, data, prompts or
  tests. Quran text comes only from the verbatim store (`retrieval/verbatim.py`,
  built from Quranpedia); hadith only from the HadeethEnc store (`get_hadith`, built by
  `ingest/hadeethenc.py`) or the optional Dorar tool. Tests compare
  against the store or use normalized forms.
* `retrieval/contract.py` is shared with the agent owner: do not change fields or
  signatures without both owners agreeing.
* No secrets in code. The LLM key is the env var `AI_API_KEY` (OpenAI-compatible
  endpoint `AI_BASE_URL`, default model `AI_MODEL=space-bunny-free`).
* Do not commit downloaded source texts (data/raw, processed, store, index): their
  licences allow use in apps, not redistribution as datasets. Only
  `data/glossary.json` and `data/embeddings/` are committed.
* Glossary entries are copied from Jamhara or the challenge pack only; never invent
  a translation of a term.

## Commands

```bash
. .venv/bin/activate
python -m ingest.build_all                # build everything (needs network once)
python -m ingest.build_all --only quran   # verbatim store only (fast, no models)
python -m pytest -q                       # unit tests (index-dependent ones auto-skip)
python -m eval.run_eval retrieval --rerankers none      # retrieval metrics
python -m eval.run_eval ayah                            # misquote detection
python -m eval.run_eval agent --api http://localhost:8000 --judge   # full pipeline
RETRIEVER=mock ...                        # 3 fixed evidence items, no models
```

## Map

* `retrieval/` runtime library — see docs/ARCHITECTURE.md
* `ingest/` build pipeline — download → quran → bayyinat → (shamela, hadith: opt-in) → build_index;
  Shamela book list in `ingest/shamela_books.yaml` (only the content team changes it)
* `eval/` cases + runner; results in `eval/results/`, summary in docs/EVALUATION.md
* `docs/HANDOFF.md` how the agent uses this layer; `docs/DECISIONS.md` scope decisions
* `agent/` LangGraph agent, `api/` FastAPI service — docs/AGENT.md, docs/API_INTEGRATION.md, docs/AGENT_WORKLOG.md
* `api/mueen.py` `POST /mueen/draft`: the Sheykak app's format; app + Supabase code in `integration/sheykak/`
* Agent rule: the model writes `[[Q:..]]`/`[[H:..]]` placeholders only; `agent/rules.py` + `nodes.check_draft` must keep rejecting anything else

## Conventions

* Python 3.11, type hints, small modules with a docstring explaining *why*.
* Settings only through `retrieval/config.py` (env vars, `.env`).
* Arabic normalization (`retrieval/normalize_ar.py`) is for search keys only —
  never normalize text that is displayed.
* Update docs/DISCLOSURE.md whenever a tool or model is added.
