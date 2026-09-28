---
name: knowledge-layer
description: How to use and extend Mu'een's knowledge & retrieval layer (Quran verbatim store, Bayyinat search, misquote detection, glossary, language id). Use when writing agent code that retrieves evidence, cites Quran verses, verifies citations, or when adding a new source to the index.
---

# Using the knowledge layer from agent code

```python
from retrieval import retrieve, get_verbatim            # the contract
from retrieval.config import ABSTAIN_THRESHOLD
from retrieval.langid import detect_language
from retrieval.ayah_match import find_quran_quotes, match_ayah
from retrieval.verbatim import quran_refs_in
from retrieval.glossary import glossary_for, format_for_prompt
```

1. **Language**: `lang, conf = detect_language(" ".join(seeker_messages[-3:]))`.
2. **Evidence**: `ev = retrieve([core_question, arabic_query, ...], lang, k=6)`.
   Abstain if `not ev or ev[0].score < ABSTAIN_THRESHOLD`.
   For hadith requests use `types=["hadith"]`; empty result ⇒ abstain (no hadith is stored).
3. **Misquotes**: for each `m in find_quran_quotes(last_message)` with `not m.is_exact`,
   append `get_verbatim(m.ref_id, lang)` to `ev` and tell the generator to show the
   correct wording gently.
4. **Placeholders**: the model writes `[[Q:2:144]]`, never verse text. Allowed ids =
   `{e.id for e in ev}` ∪ `quran_refs_in(e.text_ar)` for Bayyinat evidence.
   Resolve with `get_verbatim(id, lang)`; `None` ⇒ verification issue.
5. **Rendering**: Quran as `﴿text_ar﴾` + translation + `(ref)`; hadith as `«text_ar»`
   + source + grade. Never put hadith in Quran brackets.
6. **Glossary**: `format_for_prompt(glossary_for([conversation, *[e.text_ar for e in ev]], lang), lang)`.

# Adding a new source

1. Download it officially in `ingest/download.py` (verify checksums when published).
2. Write `ingest/<source>.py` producing `WORK_DIR/processed/<source>.jsonl` records
   with `id, type, text_ar, translations, source, ref, grade, source_url` (+ `title`).
   Ids must be unique and stable (`TYPE:source:n`).
3. Add `embed_text`/`bm25_text` handling in `ingest/build_index.py` if the type is new.
4. `python -m ingest.build_all`, then add cases to `eval/retrieval_cases.yaml` and
   re-run `python -m eval.run_eval retrieval`; re-tune `ABSTAIN_THRESHOLDS` if needed.
5. Record the source in docs/SOURCES.md and any tool in docs/DISCLOSURE.md.
