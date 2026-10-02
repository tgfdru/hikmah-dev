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

### `POST /suggest` — draft a reply for the latest seeker message

Request:

```json
{
  "conversation_id": "site-conv-8841",
  "messages": [
    {"role": "seeker", "text": "Why do Muslims worship the Kaaba?"}
  ]
}
```

* `role`: `seeker` (the person asking) or `dai` (the da'i). Oldest first; the last
  seeker message is the one answered. Send the recent part of the conversation (up to 50
  messages; the assistant reads the last 8).
* `conversation_id`: the site's own id (pseudonymous; no names, emails or phones).

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
  "analysis": {"language": "en", "knowledge_level": "beginner", "tone": "curious",
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

## 4. Errors

| HTTP | Meaning | What to do |
|---|---|---|
| 401 | Missing/wrong `X-API-Key` | Check the server's key |
| 403 | The service period has ended | Contact the service owner |
| 422 | Invalid body (e.g. empty messages, unknown role or style) | Fix the request |
| 502 | The assistant failed for this request | Let the da'i retry or answer manually |
| 503 | The service is not configured (LLM key missing) | Contact the service owner |

Timeouts: allow up to 60 s per request; drafting uses several model calls.

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
