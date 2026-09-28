# Privacy

Challenge rule (الخصوصية): collect personal or sensitive data only as needed, under
a published policy, and never use it to draw unnecessary conclusions about the user.

## What the knowledge layer stores

* **Nothing about users.** `retrieve()`, `get_verbatim()`, `detect_language()` and
  `match_ayah()` are pure functions over the approved sources. They keep no logs of
  queries.
* The optional Dorar tool caches **hadith returned by Dorar** (text, source, grade)
  in `WORK_DIR/cache/hadith.sqlite` so the verifier can resolve them. It does not
  store the query or who asked.
* Search queries are sent to external services only when the Dorar tool is enabled
  (Arabic search terms to dorar.net). The LLM-judge in `eval/` sends only the test
  cases in this repo.

## Recommendations for the agent/API layer

1. **Log ids and metrics, not conversations.** For evaluation and the "acceptance
   rate" metric, `/feedback` needs `conversation_id`, `suggestion_id`, `action`,
   level, cited ids and latency. Seeker messages are not needed; if kept for debugging,
   set a short retention (e.g. 30 days) and delete automatically.
2. **Level D messages are the sensitive ones** (marriage, divorce, health,
   inheritance). Do not persist their text.
3. **The inferred `background` / `knowledge_level` is session-only.** Never build a
   profile of a seeker's religion or beliefs across conversations.
4. **Pseudonymous ids only.** Use the website's conversation id; no names, phone
   numbers or emails in the AI service.
5. **LLM provider**: conversation text is sent to the configured LLM API
   (OpenCode Zen) to draft replies. State this in the site's privacy policy.
6. **Transparency**: the seeker talks to a human da'i; the AI only drafts for the
   da'i. The site should say that the team uses AI tools with human review.
