# Connecting Mu'een to the Sheykak app — plan and code (2026-10-06)

```
Sheykak app ──(scholar's session)──► Supabase Edge Function `mueen-draft` ──(X-API-Key)──► Mu'een API
  api/http-service.ts                 checks: signed in, scholar, may answer         POST /mueen/draft
                                      holds MUEEN_API_KEY (never in the app)         (Dokploy server)
```

The app keeps its `MueenService` interface; only `src/features/mueen/api/index.ts` changes from
the mock to the live client. The Mu'een API answers in the app's own `MueenDraft` shape
(docs/API_INTEGRATION.md, `POST /mueen/draft`).

Files here, to copy:

| File | Goes to |
|---|---|
| `supabase/functions/mueen-draft/index.ts` | the Supabase project (`supabase/functions/mueen-draft/`) |
| `app/src/features/mueen/api/http-service.ts` | Sheykak app, same path (new file) |
| `app/src/features/mueen/api/index.ts` | Sheykak app, same path (replaces the mock export) |

Both TypeScript files were type-checked (`tsc --strict` against supabase-js 2 and the app's
`types.ts`; `deno check` for the function).

## 1. Server (Fawaz)

1. **Deploy the new code:** switch Dokploy's branch to `claude/loving-heisenberg-oekuju` (it
   contains all of `nader/agent` up to 2026-10-06 12:53) and redeploy.
2. **Hadith (new):** `kb-build` now fetches HadeethEnc once into the volume (`HADITH=1`, the
   default). The **first** deploy after this takes about an hour longer; later deploys reuse it.
   If the HadeethEnc site is down the build continues without hadith.
3. **Shamela:** check the `kb-build` log of the last deploy for
   `bm25 + docs: … 'dawah': 6766`. If `dawah` is missing, the Shamela seed was not mounted
   (see `ingest/kb_entry.sh`, Nader set this up).
4. **A key for Supabase:** `openssl rand -hex 24`, then add it to `MUEEN_API_KEYS` in Dokploy
   (comma-separated with the existing key) and redeploy. Give it only to step 2.
5. Check: `https://mueen.fawazabdullah.dev/health` → `"status": "ok"`, `"models_loaded": true`.

## 2. Supabase (Fawaz)

1. Create the function `mueen-draft` with `supabase/functions/mueen-draft/index.ts`
   (Dashboard → Edge Functions → Deploy a new function, or `supabase functions deploy mueen-draft`).
   Keep **"Verify JWT" on**.
2. Secrets (Edge Functions → Secrets):
   * `MUEEN_API_URL` = `https://mueen.fawazabdullah.dev`
   * `MUEEN_API_KEY` = the key from step 1.4
3. Who may draft (already set for Sheykak's schema): an **active scholar**
   (`profiles.role = 'scholar'`, `profiles.status = 'active'`) who is **assigned** to the
   question (`question_assignments.question_id` / `scholar_id`). Both checks use the
   scholar's own session, so Sheykak's Row Level Security rules apply.
4. Limits to know: Supabase stops a function after 150 s on the free plan; a draft takes
   ~30-60 s, so this fits. The function logs only status codes, never message text.

## 3. App (pull request to Sheykak-Mueen)

1. Copy `http-service.ts` and `index.ts` (table above). `EXPO_PUBLIC_MUEEN_MOCK=1` brings
   the sample answer back for UI work.
2. **Types** (`types.ts`) — optional fields the API already sends:
   ```ts
   export interface MueenSource { /* … */ translation?: string }          // approved translation of the quote
   export interface MueenDraft {
     /* … */
     status?: "ok" | "unverified" | "abstain" | "refer";
     level?: "A" | "B" | "C" | "D";
     notice?: string;          // Arabic note for the scholar
     reviewPoints?: string[];  // claims the checkers asked the scholar to check
   }
   ```
3. **No-draft state** (`MueenDraftBody`): when `paragraphs` is empty, show a message such as
   "لم يجد معين في المصادر المعتمدة ما يكفي لإعداد مسودة — يمكنك الإجابة بنفسك" plus
   `draft.notice`, and keep "Send" disabled. This happens when the sources have no answer
   (`abstain`) or the question asks for a verdict on persons or groups (`refer`).
4. **Scholar notice:** show `draft.notice` as a small banner above the paragraphs when
   `status === "unverified"` (the draft failed the automatic checks) or `level === "D"`
   (a personal case: general evidence only, the ruling is the scholar's). Optional: list
   `reviewPoints` under it.
5. **Citations sheet:** show `source.translation` under the quote when present (English/Urdu
   askers). Hadith from HadeethEnc come as `kind: "other"` with `grade`; a dedicated badge
   (e.g. `kind: "hadeethenc"`) can be added later if you want one — tell Fawaz.
6. **Waiting time:** a draft takes ~30-60 s. Update `sheet.loading` (e.g. "قد يستغرق ذلك
   حتى دقيقة") and set `retry` in `useMueenDraft` to retry only network errors, so a failed
   one-minute draft is not silently repeated:
   ```ts
   retry: (count, err) => count < 1 && err instanceof MueenDraftError && err.code === "network",
   ```
7. Run the app's checks: `tsc --noEmit`, `jest`, i18n parity (new strings in `ar` and `en`).

## 4. What each paragraph looks like

* Paragraph text: the model's explanation. A verse or hadith is **not** written in the text;
  a short reference stands in its place — "(البقرة: 144)", "(Quran 2:144)", "(حديث)".
* Its chips: the exact verse (`quote` in ﴿﴾, from the verified Quran store), hadith (`quote`
  in «», with grade and attribution, from HadeethEnc), the Shamela book and page, the
  Bayyinat question, or a glossary term — each with a link.
* The scholar edits freely; sources stay attached to their paragraph.

## 5. Test checklist (end to end)

| Case | Expected |
|---|---|
| "Why do Muslims face the Kaaba?" | paragraphs with Quran chips (البقرة 144…) and the Bayyinat question |
| "Is Jesus the son of God? Was he crucified?" | Quran (التوبة 30, مريم 34, النساء 157) + Shamela chips |
| "Give me a hadith about intentions" | a HadeethEnc chip with grade صحيح |
| A personal case ("my husband …, what should I do?") | `level: "D"`, banner, general evidence only, no ruling |
| "Is [named group] misguided?" | no paragraphs, notice explains it is out of scope |
| "What is the capital of France?" | no paragraphs, notice: nothing in the approved sources |
| Signed in as a non-scholar | 403, chip shows the error state |
