# Integration guide for sheykak.com

For the web team connecting the da'i inbox on sheykak.com to the Mu'een assistant.
The assistant **drafts**; the da'i reviews, edits and sends. Nothing is ever sent to
a seeker automatically.

## 1. How to call it

* Call the API **from the site's server**, never from the browser: the API key must
  stay on the server.
* Base URL: provided by the service owner (Nader). All requests are JSON.
* Header on every call except `/health`: `X-API-Key: <key provided by the service owner>`.

## 2. Endpoints

### `POST /suggest` — draft a reply

Two modes, matching the two buttons in the da'i's chat:

| UI action | Send | What is answered | Reply language |
|---|---|---|---|
| **AI reply to a message** (the da'i picked a seeker message) | `"reply_mode": "message"`, `"target_message_id": "<that message's id>"` | exactly that message (later messages are ignored) | the language of that message |
| **AI reply for the conversation** (nothing picked) | `"reply_mode": "conversation"` (default) | the latest seeker message | the language of the latest meaningful seeker message |

Request (message mode):

```json
{
  "conversation_id": "site-conv-8841",
  "reply_mode": "message",
  "target_message_id": "m-1093",
  "messages": [
    {"id": "m-1090", "role": "seeker", "text": "السلام عليكم، عندي سؤال"},
    {"id": "m-1091", "role": "dai",    "text": "وعليكم السلام، تفضل"},
    {"id": "m-1093", "role": "seeker", "text": "What about the marriage of Muhammad to Aisha?"}
  ],
  "conversation_language": null,
  "seeker_profile_language": "en"
}
```

* `messages`: oldest first, up to 50, **each with the site's message `id`**. `role`: `seeker` (the person
  asking) or `dai`. Send the conversation **as it is** — do not translate it, and send the picked message in
  its original text.
* `reply_mode` / `target_message_id`: `target_message_id` is required in message mode and must be the id of a
  **seeker** message present in `messages` (otherwise 422).
* `conversation_language`, `seeker_profile_language` (optional, ISO 639-1): fallbacks only, used when no
  message has enough text to identify its language (e.g. "Why?", "نعم"). **Never send the app UI language or the
  da'i's language** in these fields.
* Old requests without `reply_mode` / `id` keep working (conversation mode).
* `conversation_id`: the site's own id (pseudonymous; no names, emails or phones).

How the language is chosen (one function, `agent/language.py`): the answered message → its neighbouring seeker
messages (message mode) → the recent meaningful seeker messages → `conversation_language` → profile language.
A message counts only if it has ≥ 10 letters and a confident detection. The language of the religious sources
never decides the reply language: an English question answered from an Arabic source gets an English reply.
`analysis.language_source` in the response says which rule decided (`target_message`, `nearby_message`,
`recent_messages`, `conversation`, `profile`, `default`).

Response (fields the UI needs):

```json
{
  "conversation_id": "site-conv-8841",
  "suggestion_id": "s_3f9a1c2b7d10",
  "status": "ok",
  "level": "A",
  "reply": "…draft in the seeker's language, with the verse text inserted…",
  "reply_ar": "…Arabic version for the da'i…",
  "note_for_dai": "…short note in Arabic for the da'i…",
  "analysis": {"language": "en", "language_source": "target_message", "knowledge_level": "beginner", "tone": "curious",
               "core_question": "…", "level_reason": "…"},
  "citations": [
    {"id": "Q:2:144", "type": "quran", "source": "القرآن الكريم", "ref": "البقرة: 144",
     "source_url": "https://quranpedia.net/…", "grade": null}
  ],
  "issues": [],
  "latency_ms": 0,
  "ai_generated": true,
  "disclaimer": "مسودة مقترحة من مساعد ذكاء اصطناعي — يراجعها الداعية ويعدّلها قبل الإرسال."
}
```

### `POST /suggest/regenerate`

Same body plus `"style": "simpler" | "deeper" | "shorter"`.

### `POST /feedback` — what the da'i did with the draft

```json
{"conversation_id": "site-conv-8841", "suggestion_id": "s_3f9a1c2b7d10",
 "action": "sent_as_is", "edit_ratio": 0.0}
```

`action`: `sent_as_is` | `edited` | `rejected`. `edit_ratio` (optional, 0–1) = share of
the text the da'i changed. Do **not** send the edited text. This feeds the "accepted
without major edits" metric (`GET /stats`).

### `GET /health`

No key. Shows whether the models and the verbatim store are loaded and the service end date.

## 3. How the UI should show each status

| `status` | Show to the da'i | Suggested badge |
|---|---|---|
| `ok` | The draft in an editable box + the citations as clickable links (`source_url`) | level A / B / C |
| `unverified` | The draft **with a warning**: "لم تجتز المسودة التحقق — راجع المراجع" + `issues` | ⚠ yellow |
| `refer` | The referral text (no ruling) + `note_for_dai` | 🔴 D — فتوى/حالة شخصية |
| `abstain` | The "no reliable source" text + `note_for_dai` | ⚪ no source |

Also:
* Always show `disclaimer` near the draft.
* Show `reply_ar` to the da'i when the seeker writes in another language.
* Level `C`: suggest the da'i double-check with a specialist.
* `ok` with non-empty `issues` (entries starting "not in the evidence:"): an independent model found
  details that the sources do not state. Show them as review points under the draft (🔎) — the
  draft is still usable after the da'i checks them. `note_for_dai` already mentions them.

## 4. Errors

| HTTP | Meaning | What to do |
|---|---|---|
| 401 | Missing/wrong `X-API-Key` | Check the server's key |
| 403 | The service period has ended | Contact the service owner |
| 422 | Invalid body (e.g. empty messages, unknown role or style) | Fix the request |
| 502 | The assistant failed for this request | Let the da'i retry or answer manually |
| 503 | The service is not configured (LLM key missing) | Contact the service owner |

Timeouts: allow up to **180 s** per request (typical 20–60 s; drafting uses several model calls plus an independent check). Show a "preparing a draft…" state; never block the da'i's own typing.

## 5. Privacy and transparency (for the site's policy page)

* The site sends conversation text to the assistant, which sends it to the configured
  LLM provider to draft the reply. The assistant does not store message or reply text;
  it logs ids, levels, cited sources and timing only.
* Seekers talk to a human da'i. The site should state that the team uses AI tools to
  help draft replies, with human review.

## 6. Service ownership

The service is operated by its owner (Nader Al-Shehri), who issues the API keys. Keys
can be revoked, and the service can have an end date (`MUEEN_SERVICE_UNTIL`) covering the
hackathon and judging period. **The period and the terms of use after it must be agreed
in writing by the team** (status: to be agreed).
