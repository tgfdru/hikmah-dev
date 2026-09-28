# Safety: how the knowledge layer supports the challenge's rules

## Response levels (from the reference pack)

| Level | Scope | Required handling | What this layer provides |
|---|---|---|---|
| A | Quran, authentic hadith, pillars, basic seerah, morals | Direct answer with a source | Verbatim Quran store with approved translations; Bayyinat passages; exact ids for citations |
| B | Explanations, comparisons, general doubts | Answer from approved material, show the reference, no certainty where scholars differ | Bayyinat (263 questions on doubts) with page-level links |
| C | Disputed or highly sensitive matters | Restricted answer, mention the disagreement, or refer | Same evidence; the agent's router decides the level (e.g. apostasy, sectarian history are in Bayyinat but must be handled as C) |
| D | Personal fatwa, individual cases | No ruling; general information + referral | Nothing to retrieve for the ruling itself; referral text: "consult a qualified local scholar or your da'wa association" |

## Binding standards → mechanisms

| Standard (المعيار العلمي الملزم) | Mechanism in this repo |
|---|---|
| Reliability & attribution: every quote traceable; never attribute text to a source that does not contain it | `get_verbatim()` is the only source of Quran text; every `Evidence` has `source`, `ref` and `source_url` (Bayyinat links to the exact PDF page). Unknown ids return `None`. |
| Distinguish scripture from generated explanation | Evidence carries `type`; Quran text comes from the store, never from the model (placeholders `[[Q:…]]` are resolved by the agent). |
| Do not present disputed matters as certain | Level C handling is in the agent; Bayyinat evidence is labelled with its question so the da'i sees the context. |
| No independent fatwa | Level D routing is in the agent; this layer has no fatwa content (Quranpedia fatwa files were deliberately not ingested). |
| Hallucination resistance: prefer abstaining when evidence is missing or weak | Every evidence has a 0–1 score; `ABSTAIN_THRESHOLD` is tuned on answerable vs unanswerable questions (docs/EVALUATION.md). No hadith exists in the store, so requests for hadith cannot be "answered" with invented text. `match_ayah` catches Quran-like text written by the model. |
| Da'wah quality: audience, level, language | Evidence available in Arabic, English and Urdu; language detection for the seeker. |
| Translation & localisation: keep the Islamic meaning of terms | `data/glossary.json`: the pack's 10 terms with usage rules + Jamhara equivalents; `glossary_for()` injects only relevant terms. |
| Transparency | Documented in `docs/DISCLOSURE.md`; the seeker only ever talks to a human da'i. |
| Privacy | See `docs/PRIVACY.md`. |

## Hadith

The approved sources require "no hadith without a source and an approved grade".
Hadith could not be downloaded from an approved source, so none are stored. The
optional Dorar tool (off by default) keeps only authentic grades and resolves
through the same verbatim path. With it off, the correct behaviour for any hadith
request is to say that no matching hadith was found in the approved sources.

## Known limits (be honest in the demo)

* Bayyinat covers 263 frequent questions; anything else falls back to Quran verses
  only, where the evidence is thinner and abstaining is more likely.
* Tafsir, fiqh encyclopedias and the Dorar aqeeda/history sections are not included.
* The Jamhara glossary entries are copied verbatim but have not yet been reviewed
  by the team's content member.
