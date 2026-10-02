# Agent layer (Nader's part)

The agent turns a conversation between a da'i and a seeker into a **draft reply the
da'i reviews before sending**. It is a LangGraph state machine on top of the
knowledge layer (`retrieval/`, see HANDOFF.md). Code: `agent/`, HTTP API: `api/`.

## 1. Pipeline

```
analyze ─► route ──(D)──────────────────────────────► refer (personal) ──► END
               └─► retrieve ──(no evidence / no hadith)► abstain ──► END
                        ├──(level C, no evidence)──────► refer (specialist) ► END
                        ├──(term question, glossary only)► generate
                        └─► generate ─► verify ──(issues, attempt 1)─► generate
                                            └─► END  (ok | unverified)
```

| # | Stage | File | What it does | LLM? |
|---|---|---|---|---|
| 1 | Context Analyzer | `agent/nodes.py:analyze` | Seeker's language (fastText, LLM fallback), knowledge level, tone, background (session only), real question, Arabic search query, hadith request, personal case; detects (mis)quoted verses with `find_quran_quotes` | yes (`Analysis`) |
| 2 | Safety Router | `nodes.py:route` | Level A–D from the challenge pack. The keyword rule (`rules.level_d_hint`: first person **and** ruling word **and** personal circumstance) is only a hint; when the analyzer **and** the rule both see a personal case the level is raised to D (pack: "choose the more cautious level") | yes (`Routing`) |
| 3 | Hybrid Retriever | `nodes.py:retrieve` | `retrieve([seeker words, Arabic query, core question], lang)`; keeps evidence ≥ `ABSTAIN_THRESHOLD`; hadith requests use `types=["hadith"]` only; adds the correct verse of a misquote from `get_verbatim` | no |
| 4 | Draft Generator | `nodes.py:generate` | Draft in the seeker's language + Arabic copy + note for the da'i; level-specific rules; relevant glossary terms (`glossary_for`); Quran/hadith **only as placeholders** `[[Q:2:144]]` | yes (`Draft`) |
| 5 | Citation Verifier | `nodes.py:verify` / `check_draft` | Deterministic checks (below), optional LLM judge (`VERIFY_LLM_JUDGE=1`); replaces placeholders with the exact text from the store | optional (`Judgement`) |
| – | Refer | `nodes.py:refer` | Level D: fixed personal-case template; Level C with no evidence: fixed "ask a specialist" template (`agent/templates.py`). No ruling, no generation | only to translate a template into a language without one |
| – | Abstain | `nodes.py:abstain` | No evidence above the threshold, or a hadith request with no authentic hadith in the sources | same |

Typical LLM calls per request: 3 (analyze, route, generate) + 1 per retry
(+1 with the judge). Refer/abstain stop after 2.

## 2. Hard guarantees (deterministic, unit-tested)

These do not depend on the model behaving well (`agent/rules.py`, `check_draft`):

1. **No model-written scripture.** Every `[[Q:…]]`/`[[H:…]]` placeholder must be in the
   retrieved evidence (or a verse quoted inside a cited Bayyinat passage,
   `quran_refs_in`) **and** resolve in the verbatim store (`get_verbatim`). Anything else
   is rejected. Verse text in the final reply is always the store's text.
   *Repair:* if the model typed a verse that **is** in the evidence, the verifier replaces
   that span with its placeholder (so the store's exact text is shown) before checking.
2. **No scripture typed by the model.** The Quran brackets `﴿ ﴾` outside a placeholder,
   or Arabic text that matches an ayah (`find_quran_quotes`) outside a placeholder → rejected.
3. **Every cited id is real.** `cited_ids` must be retrieved evidence ids.
4. **Level C** drafts may not claim consensus/certainty (`rules.CERTAINTY_PHRASES`).
5. **Rendering**: `﴿…﴾ [surah: ayah]` + approved translation for Quran; hadith in `«…»`
   with source and grade (HANDOFF §5.1).
6. **Retry once, then show "unverified".** A draft that fails twice is returned with
   `status: "unverified"`, the issues, and unresolved placeholders replaced by
   `[⚠ unverified reference — check]` (DECISIONS: shown to the da'i, not hidden).
7. **Level D never reaches the generator**; hadith requests never fall back to
   Quran/Bayyinat evidence (HANDOFF §5.7).

### Glossary path (term questions)

"What does Tawhid mean?" or "Translate الشريعة" often has no search hit above the
threshold, but the approved **glossary** (challenge pack + Jamhara, `data/glossary.json`)
answers it. When the analyzer marks `asks_term_meaning` and names the term
(`asked_term`), and the glossary has it, the generator drafts from the glossary entry
and cites it as `GL:<jamhara id>` (type `glossary` in `citations`). The verifier accepts
`GL:` ids only for entries that were given to the generator.

### Robust structured output

`space-bunny-free` sometimes returns a malformed tool call (fields nested inside another
field) or none at all. `agent/llm.py:structured` lifts nested fields back to the top
level when that makes the output valid, otherwise retries (up to 3 calls) before failing
the request with a clear error.

## 3. Status values returned

| status | Meaning | What the da'i sees |
|---|---|---|
| `ok` | Draft passed verification | Draft + sources |
| `unverified` | Failed verification twice | Draft with ⚠ marks + list of issues |
| `refer` | Level D, or Level C without evidence | Fixed referral text (no ruling) + red/orange note |
| `abstain` | Not enough evidence / no authentic hadith | Fixed "no reliable source" text + note |

## 4. Configuration (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL` | OpenCode Zen, –, `space-bunny-free` | LLM endpoint (OpenAI-compatible) |
| `AI_MODEL_ANALYZE` / `_ROUTE` / `_GENERATE` / `_JUDGE` | `AI_MODEL` | Per-stage model override |
| `RETRIEVER` | `hybrid` | `mock` = 3 fixed items, no models (development, tests) |
| `ABSTAIN_THRESHOLD` | per reranker (0.35 for `minilm`) | Below this best score → abstain |
| `MAX_DRAFT_ATTEMPTS` | `2` | Drafts before "unverified" |
| `VERIFY_LLM_JUDGE` | `0` | Second verification layer (one more LLM call) |
| `MUEEN_API_KEYS` | empty | Accepted `X-API-Key` values; empty = no check (dev only) |
| `MUEEN_SERVICE_UNTIL` | empty | Last day the service answers (YYYY-MM-DD) |
| `MUEEN_RUN_LOG` | `1` | Privacy-safe JSONL log in `WORK_DIR/logs/runs.jsonl` |

Structured output always uses `method="function_calling"` (`agent/llm.py`) because
`space-bunny-free` ignores JSON-schema mode (HANDOFF §4).

## 5. Prompts and templates (to be reviewed)

* `agent/prompts/*.md` — one file per LLM stage, readable without code. The level
  definitions in `route.md` are copied from the challenge reference pack.
* `agent/templates.py` — referral and abstain texts in ar / en / ur / id / fr.

**Review status:** written by the agent owner; **pending review by the team's
content/sharia reviewer** before the demo.

## 6. Privacy

Follows docs/PRIVACY.md: the run log stores conversation id, suggestion id, level,
status, language, cited ids, number of issues, attempts, best score, latency and the
stage trace — **no message text, no reply text**. `/feedback` stores the action and an
optional edit ratio, not the edited text. The inferred background/knowledge level is
used inside the request only.

## 7. Tests

```bash
python -m pytest -q tests/test_agent_rules.py tests/test_agent_graph.py tests/test_api.py
```

The graph tests run fully offline with `RETRIEVER=mock` and a scripted LLM
(`tests/agent_fakes.py`): happy path, fabricated reference → retry, double failure →
unverified, model-written brackets, Level C consensus claim, Level D referral,
hadith request → abstain, low confidence → abstain, template translation,
regenerate style, API key, service end date, privacy of the run log.

## 8. Known limits

* Latency: 3 sequential LLM calls + retrieval (retrieval measured by the knowledge
  layer at ≈1.7 s on CPU with `minilm`). End-to-end latency is **not measured yet** —
  it will be reported in EVALUATION.md §4. A faster model per stage can be set with `AI_MODEL_*`.
* Hadith: none in the store while Dorar is off (see DECISIONS); hadith requests abstain.
* Translations of verses exist for `en`/`ur`; other languages get English.
