# Disclosure: tools and models

Required by the challenge: every tool and model, its type, source, role and the
pipeline stage it serves. Stages follow the plan: 1 Context Analyzer, 2 Safety
Router, 3 Hybrid Retriever, 4 Draft Generator, 5 Citation Verifier.
Any tool added later must be added here immediately.

## Knowledge & retrieval layer (this repository)

| Tool / model | Type | Source | Role | Stage |
|---|---|---|---|---|
| BGE-M3 (`BAAI/bge-m3`) | Multilingual embedding model, open weights (MIT) | huggingface.co/BAAI/bge-m3 | Turns passages and queries (Arabic, English, Urdu, …) into vectors in one space | Indexing, 3 |
| bge-reranker-v2-m3 (`BAAI/bge-reranker-v2-m3`) | Cross-encoder reranker, open weights (Apache-2.0) | huggingface.co/BAAI | Optional (`RERANKER=bge`): scores evidence relevance 0-1 for the abstain decision | 3 |
| mMiniLM reranker (`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`) | Small multilingual cross-encoder (Apache-2.0) | huggingface.co/cross-encoder | Optional (`RERANKER=minilm`): faster reranking on CPU | 3 |
| fastText lid.176 | Language identification model (CC BY-SA 3.0) | fasttext.cc (Meta) | Detects the seeker's language offline | 1 |
| Qdrant (server v1.19.1, `qdrant-client`) | Vector database, open source (Apache-2.0) | qdrant.tech | Dense search with source-type filters | 3 |
| rank_bm25 + our Arabic normalization | Keyword search (Apache-2.0) | PyPI | Exact-term matching (names, terms, surah names) | 3 |
| Reciprocal Rank Fusion | Algorithm (our code) | Cormack et al., 2009 | Merges dense and keyword results | 3 |
| RapidFuzz | Fuzzy string matching (MIT) | PyPI | Detects misquoted ayahs (`match_ayah`) | 1, 5 |
| PyMuPDF | PDF text extraction (AGPL-3.0) | PyPI | Extracts the Bayyinat book at build time only (not shipped in the runtime path) | Ingestion |
| sentence-transformers / PyTorch (CPU) | ML runtime | PyPI | Runs BGE-M3 and rerankers | Indexing, 3 |
| SQLite | Database | Python stdlib | Verbatim store: single source of truth for Quran text | 5 |
| Pydantic | Data validation | PyPI | `Evidence` contract shared with the agent | 3, 4, 5 |
| `space-bunny-free` via OpenCode Zen | LLM behind an OpenAI-compatible API | opencode.ai/zen | Evaluation only: LLM-judge of faithfulness and tone | Evaluation |
| Dorar hadith API (optional, off) | Public search API | dorar.net | Live search of graded hadith when enabled | 3 |

## Agent layer (`agent/`, `api/` — Nader)

| Tool / model | Type | Source | Role | Stage |
|---|---|---|---|---|
| `space-bunny-free` (default; any model on the same endpoint via `AI_MODEL` / `AI_MODEL_<STAGE>`) | LLM via OpenAI-compatible API | opencode.ai/zen | Context analysis (`Analysis`), level routing (`Routing`), drafting (`Draft`), optional faithfulness judge (`Judgement`); translates the fixed referral/abstain templates into languages that have no reviewed version | 1, 2, 4, 5 |
| LangGraph | Agent orchestration library (MIT) | LangChain Inc. / PyPI | State graph of the stages: analyze → route → retrieve → generate → verify, with refer / abstain branches and one retry | 1–5 |
| langchain-openai / langchain-core | LLM client (MIT) | PyPI | Calls the endpoint; structured output with `method="function_calling"` | 1, 2, 4, 5 |
| Pydantic | Data validation (MIT) | PyPI | Schemas of every LLM output and of the API | 1–5, API |
| FastAPI + Uvicorn | Web framework + ASGI server (MIT / BSD) | PyPI | `/suggest`, `/suggest/regenerate`, `/feedback`, `/stats`, `/health`; API-key check and service end date | API |
| fastText lid.176 (from the knowledge layer) | Language identification | fasttext.cc (Meta) | Seeker's language; the LLM's answer is the fallback | 1 |
| RapidFuzz via `find_quran_quotes` (knowledge layer) | Fuzzy matching | PyPI | Detects misquoted verses in the seeker's message; detects Quran-like text the model wrote outside a placeholder | 1, 5 |
| Verbatim store via `get_verbatim` (knowledge layer) | SQLite lookup | Quranpedia (King Fahd Complex print) | The only source of verse text in replies; deterministic check that every reference exists | 5 |
| Regular-expression rules (our code, `agent/rules.py`) | Deterministic rules | — | Level-D hint, placeholder parsing, range coverage, consensus-claim check, rendering | 2, 5 |
| Docker (`Dockerfile.api`, compose service `api`) | Packaging | docker.com | Deployment of the API next to Qdrant | Deployment |

## AI-assisted development

Parts of this repository's code and documentation were written with Claude Code
(Anthropic), reviewed by the team. Recorded here per the plan's rule that
AI-assisted programming tools are disclosed too.

## Not used (changed from the original plan)

* ALLaM / any self-hosted "sovereign" model — dropped for time.
* Telegram bot — the assistant is integrated into the team's website instead.
