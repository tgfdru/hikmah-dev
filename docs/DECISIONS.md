# Decisions log (Fawaz's part — Knowledge & Retrieval)

Changes from the original plan (`docs/reference/plan.md`), agreed with Fawaz on 2026-09-28.

## Scope
- This branch delivers **Fawaz's part only**: `ingest/`, `retrieval/`, `data/`, `eval/` + docs.
  Nader builds the agent (`agent/`) and the API (`api/`, `/suggest` etc.) on top of it.
- `retrieval/contract.py` follows the plan's agreed interface (`Evidence`, `retrieve`, `get_verbatim`).
- Deliverable: code ready for the team to deploy (no deployment by us). Hand-off to Nader tonight.
- No Telegram bot (the product is integrated into sheykak.com by the web team).
- No sovereign / self-hosted LLM (ALLaM dropped).

## LLM
- Provider: OpenCode Zen, OpenAI-compatible API at `https://opencode.ai/zen/v1`.
- Key in env var `AI_API_KEY`; model `space-bunny-free` (for testing).
- Used in this part only for the evaluation's LLM-judge.

## Sources
- **Verbatim store = Quran only.**
  - Arabic text: Quranpedia dump `mushafs-1` (Hafs, matches King Fahd Complex print), version 2026-09-28.
  - English: Quranpedia translation book 1948 (Hilali–Khan, published by King Fahd Complex).
  - Urdu (3rd language): Quranpedia translation book 1966 (Muhammad Ibrahim Junagarhi, published by King Fahd Complex).
- **Search index (RAG)**: Quran + Bayyinat (dawa.center/file/7937, Usul Center) + glossary.
- **Hadith**: optional live Dorar search tool, **off by default**. dorar.net blocks cloud servers
  (Cloudflare 403) so it could not be tested from the dev container.
- **Glossary**: the 10 official terms from the challenge pack (authoritative), plus terms whose
  English equivalent is published by Jamhara (islamic-content.com/dictionary), each with its source URL.
  Nothing invented; content-team review recommended.

## Behaviour
- Draft failing verification twice → shown to the da'i with an "unverified" warning (not hidden).
- Level D referral → general information + "consult a qualified local scholar or your da'wa association".
- Religious review of prompts/eval outputs: a team member.

## Repo
- Work is pushed to branch `claude/loving-heisenberg-oekuju`.
