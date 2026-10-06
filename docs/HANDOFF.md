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

---

## 🆕 Update — 2026-10-05 (results added 2026-10-06) — read this part first

Everything below is new since the first handoff. Items marked **Action** need a change
or a decision on your side.

### A. New source: selected Shamela books (type `dawah`)

* 33 books from the official Shamela database, chosen with you and Shaker
  (`ingest/shamela_books.yaml`, rules at the top): 24 answering other religions and
  modern ideologies + 9 creed works from the first three centuries. Inner-Muslim
  polemics and books about named persons are left out (pack: "judging persons and
  groups" is out of scope). **6,766 passages**, ~1,400 characters each.
* Ids: `SH:<book>:<page>` (and `SH:<book>:<page>:2`, `:3` … when one page gives several
  passages). `ref` = `"<title>، ج 2 ص 531"` (printed volume/page; title only for 20
  passages without a printed page). `source_url` = the page on shamela.ws.
  `translation` is `None` (Arabic only). `contract.py` is unchanged.
* `retrieve()` now includes `dawah` by default (`types=None`), at most 2 passages per
  book per result (same as per Bayyinat question). Pass `types=["quran", "qa"]` to
  exclude it.
* Build: `python -m ingest.build_all --shamela` (or `--only shamela`). Needs **Java 21+**
  and a one-time ~4.8 GB download, ~25 min. The Docker image has no Java, so on the
  server either install a JDK and run it there, or build `processed/shamela.jsonl` (18 MB)
  on any machine and copy it into the `mueen_kb` volume under `processed/`, then run
  `kb-build` with `--only index`. The embedding cache for these passages is committed,
  so indexing takes minutes. Afterwards `raw/shamela/` (~5 GB) can be deleted.
* **Changed in your files (small, please check):**
  - `agent/nodes.py`: `_evidence_block` and `_allowed_ids` treat `dawah` like `qa`, so
    verses a Shamela passage cites ("[المائدة: ٥٠]") are allowed as `[[Q:..]]`.
  - `agent/prompts/generate.md` rule 4/5: `SH:` passages are explanations, like `QA:`;
    a hadith quoted inside a passage has no approved grade and must never be quoted
    (some early creed books are hadith/report collections without grades).
* `quran_refs_in` now also reads Arabic-Indic digits and refs in parentheses
  ("(الحديد: ٢٧)"), which Shamela books use.

### B. Hadith

Still waiting on Fawaz's decision: **HadeethEnc** (organiser's encyclopedia, ~4,000
authentic hadith with grade, explanation and approved translations — recommended) or
**Sahih al-Bukhari & Muslim from Shamela** (Arabic only). Either way it will resolve
through `get_verbatim("H:…")` like the Quran. Until then, hadith requests should keep
routing to `abstain`.

### C. Fixes on my side after your evaluation

* My checkers caused three false alarms in your runs: 3-ayah quotes, a verse and its
  reference in one parenthesis, and an Urdu reply detected as English. All fixed
  (EVALUATION.md §4.4).
* `python -m eval.recheck eval/results/<run>.json` re-applies the fixed checks to saved
  results without calling any model: Gemini + judge 39 → **40/41**, free model 36 → 38/41.

### D. Action items for you

1. **Garbage-text guard.** One free-model reply had nonsense inside the Arabic
   ("وقد Exploration…Stem sorry.") and nothing caught it. Add a check in `verify`:
   unexpected Latin words inside an Arabic/Urdu reply (outside placeholders and glossary
   terms) → regenerate once, then `unverified`.
2. **OpenRouter** (the LLM provider the team chose): in its privacy settings allow only
   providers that **do not train on or retain** prompts. Then change `AI_BASE_URL` /
   model names and rerun `python -m eval.run_eval agent --api … --judge`.
3. **Gemini free tier** may use what is sent to improve Google's products (possibly read
   by human reviewers). Seekers' messages can be very personal, so don't use it for live
   traffic.
4. **Website team:** a draft takes ~30 s. They should show a "preparing draft…" state
   and not block the page.
5. **Content review before the demo** (a team member with religious knowledge; record
   name + notes in `docs/AGENT.md`):
   - `agent/templates.py` — fixed referral / "not found" replies in all 5 languages
   - `agent/prompts/` — the rules given to the model
   - `data/glossary.json` — the 84 terms
   - `ingest/shamela_books.yaml` — the book list
   - ~10 real replies, especially apostasy, "do all Muslims agree" and music
6. **Deployment:** ≥ 8 GB RAM, Qdrant as a server (`QDRANT_URL`), HTTPS, the API key
   only on the website's server, and a second person with access to the server.
7. Rerun your agent evaluation once Shamela is in the index (results below are for
   retrieval only).

### E. Updated sources file (organisers, 2026-10)

It adds the organiser's own platforms with APIs — worth knowing for later:
QuranEnc (approved Quran translations; the file says translations should come from the
organiser's platforms), HadeethEnc (hadith, see B), terminologyenc.com (term
translations in many languages), islamhouse, byenah, and Dorar's JSON API. Not used yet
except as noted.

### F. Retrieval evaluation with Shamela

Measured 2026-10-06 (details: docs/EVALUATION.md §5):

| | before Shamela | with Shamela |
|---|---|---|
| Recall@6 / MRR (main set, both queries) | 98% / 0.93 | 98% / 0.93 |
| Held-out Recall@6 / MRR | 100% / 1.00 | 100% / 0.88 (relevant Shamela passages now rank first on 2 questions) |
| Unanswerable correctly abstained (threshold 0.35) | 100% | 100% |
| Search time per call (CPU) | 1.7 s | **2.5 s** |
| Misquote detection | 15/15 | 15/15 |

* **Scoring change in `retrieve()`:** Arabic-only passages (Bayyinat, Shamela) are now
  scored against the **Arabic** query only (when one is given). Without this, "What is
  Ramadan?" returned an encyclopedia definition of the Rotary Club first.
* **Keep sending an Arabic query** as one of the first two queries (your analyzer's
  `arabic_query` already is the 2nd). With the seeker's English words alone, Shamela
  scores are unreliable ("Which surah mentions dinosaurs?" → 0.76 instead of 0.20).
* Peak RAM of a searching process measured at 3.4 GB; the ≥ 8 GB server advice stands.
* **Action:** rerun your agent evaluation with this index, and look at a few replies
  that cite `SH:` passages (the content reviewer too).

---

## 🆕 Update — 2026-10-06 (Sheykak app + HadeethEnc) — read this part first

Built on top of `nader/agent` (fast-forwarded, nothing of yours was changed back).
Everything is on `claude/loving-heisenberg-oekuju`; Dokploy builds `nader/agent`, so
**fast-forward `nader/agent` to it (or point Dokploy at it) and redeploy**.

### A. New: `POST /mueen/draft` (api/mueen.py)

The Sheykak app's format (paragraphs with source chips, camelCase), documented in
docs/API_INTEGRATION.md. The app reaches it through a Supabase Edge Function; that code, the
app client and the step-by-step plan are in `integration/sheykak/`.

### B. Changes in your files (small; please review)

* `agent/graph.py` — `suggest(..., audience="seeker")`. With `audience="scholar"` (only
  `/mueen/draft` uses it) level D is **drafted** from the general evidence instead of the
  referral: the person using Sheykak is a scholar who decides the ruling (Fawaz's decision).
  `/suggest` behaves as before. `suggest()` also returns `draft_reply` (placeholders),
  `draft_cited_ids`, `evidence`, `glossary_used` for the app format.
* `agent/nodes.py` — `_LEVEL_RULES["D"]` (general evidence, no ruling on the case, closing
  sentence that the ruling depends on details); level D also gets the certainty check; a
  "🔴 مستوى D" note; `verify` keeps `final_draft`.
* `agent/rules.py` — `garbled()` also rejects Latin glued to an Arabic word ("أوshares",
  "الرواياتReachنا", seen in a free-model draft); hadith already containing «» is not wrapped
  again.
* `agent/prompts/generate.md` — rule 9: cite a hadith for a hadith request only if it is
  about that topic; otherwise say none was found.
* `ingest/kb_entry.sh`, `deploy/docker-compose.dokploy.yml` — `HADITH=1` (default) fetches
  HadeethEnc once into the volume (first deploy ~1 h longer; failure does not block the build).

### C. Hadith are live (HadeethEnc)

* 3,573 hadith (صحيح / حسن) with grade, attribution and approved translations
  (en/ur/id/fr where published). Ids `H:hadeethenc:<id>`; `get_verbatim` returns the exact text,
  `grade`, `ref` (= attribution, e.g. "متفق عليه") and the translation.
* `retrieve()` includes hadith by default; your `types=["hadith"]` path for hadith requests
  now finds real hadith, and still abstains for fake ones (docs/EVALUATION.md §6).
* The contract is unchanged (type `hadith` already existed).

### D. Please rerun

Your agent evaluation on Gemini with this index (`--judge`), especially the hadith-request
cases, the Bitcoin-style fake request, and level D cases through `/mueen/draft`.
