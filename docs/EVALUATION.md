# Evaluation

All numbers below were measured on 2026-09-28 on a 4-core CPU (no GPU) with the
index built from Quranpedia dump 2026-09-28 (6,236 ayahs) and the Bayyinat book
(263 questions → 1,116 passages). Raw results: `eval/results/`.
Re-run with `python -m eval.run_eval retrieval|ayah|agent`.

## 1. Retrieval (knowledge layer alone)

Test set: `eval/retrieval_cases.yaml` — **41 answerable** questions (English, Arabic,
Urdu, Indonesian, Tagalog; the challenge's topics plus common doubts), each with the
passages a correct search should find, and **11 unanswerable** ones (off-topic, and
fake-evidence requests like "a hadith proving the Prophet used a computer").

*raw* = searching with the seeker's words only; *analyzed* = plus one Arabic
reformulation, as the agent's Context Analyzer produces.

| Scoring (`RERANKER`) | Queries | Recall@6 | MRR | Latency mean / p90 | Threshold | Answerable but abstained | Unanswerable correctly abstained |
|---|---|---|---|---|---|---|---|
| none (dense cosine) | raw | 93% | 0.79 | 0.27 / 0.36 s | 0.60 | 34% | 100% |
| none (dense cosine) | analyzed | 98% | 0.93 | 0.42 / 0.47 s | 0.62 | 5% | 100% |
| minilm, 1st query | analyzed | 98% | 0.89 | 1.1 / 1.3 s | 0.25 | 5% | 100% |
| **minilm, best of 2 queries (default)** | **analyzed** | **98%** | **0.93** | **1.7 s** | **0.30** | **2%** | **100%** |
| bge-reranker-v2-m3, 1st query | analyzed | 98% | 0.92 | 7.5 / 8.3 s | 0.10 | 12% | 100% |

**Chosen default: `RERANKER=minilm`, `RERANK_QUERIES=2`, `ABSTAIN_THRESHOLD=0.30`.**
Reasons: best separation between answerable and unanswerable questions — every
unanswerable question scored ≤ 0.27 while all answerable ones but one scored ≥ 0.69,
so the threshold has a wide safety margin — at under 2 s on CPU. Dense-only scoring
is faster (0.4 s) but its margin is thin (unanswerable up to 0.60 vs answerable from
0.53); the bge reranker is slow on CPU and, scoring only the first query, abstained
more often. With a GPU, `bge` becomes practical and should be re-tuned.

Findings:
* The Arabic reformulation matters: Recall@6 rises from 93% to 98% and MRR from
  0.79 to 0.93 (dense). Hostile phrasing ("you bow to a black rock…") and Urdu
  questions are found reliably once an Arabic query is added.
* Bayyinat is usually ranked first for doubts (e.g. "Why do Muslims worship the
  Kaaba?" → Bayyinat question 9, score 0.79 dense).
* Remaining miss: `tawhid_beginner` — the right verses (Q:112, Q:2:163…) are found by
  dense search but the reranker scores "what does the word Tawhid mean" low against
  verses. The glossary covers this case (official term with usage rule), so the agent
  should treat definition questions as glossary + Quran, not abstain.
* The fake-hadith requests are also handled structurally: no hadith are stored, so
  `retrieve(..., types=["hadith"])` returns nothing.

Caveat: thresholds were tuned on the same 52 questions they are reported on. Expect
somewhat lower numbers on new questions; re-run after adding sources or cases.

## 2. Misquoted-ayah detection

`python -m eval.run_eval ayah` — 15 cases: exact quotes, misquotes (a changed or
added word), a quote spanning two ayahs, ordinary Arabic, and a hadith text that
must not be matched to the Quran.

**15 / 15 correct.** Misquotes are detected with similarity 0.94–0.99 and the correct
reference (e.g. «قل هو الله واحد» → Q:112:1 «قُلْ هُوَ اللَّهُ أَحَدٌ»). ~0.1 s per check.

## 3. Language detection

fastText lid.176 with an English-function-word rule for short English questions.
Spot checks: Arabic, Urdu, Tagalog, French 0.93–0.99 confidence; Indonesian 0.41
(correct label); "Is Islam true?" → en (fastText alone says Malay). Single words
("Kenapa?") are unreliable — the agent should use the last few messages together.

## 4. End-to-end agent (to be filled when the agent API runs)

`eval/safety_cases.yaml`: 41 cases — the challenge's 12 official test cases plus
variants in Arabic, English, Urdu and Indonesian (personal fatwas on marriage,
divorce, health and inheritance; fake hadith and verses; hostile tone; misquotes;
disputed topics). Run:

```bash
python -m eval.run_eval agent --api http://localhost:8000 --judge
```

It reports level accuracy (A–D), routing accuracy (ok / refer / abstain), refer rate on
Level-D questions, citation accuracy (every cited id resolves in the store),
Quran-quote fidelity (every quoted verse is exact), no invented hadith, reply
language, LLM-judge faithfulness and tone (`space-bunny-free`), and latency.

| Metric | Result |
|---|---|
| Level (A–D) accuracy | _pending agent API_ |
| Routing accuracy | _pending_ |
| Level-D questions referred | _pending_ |
| Citation accuracy | _pending_ |
| Quran quotes exact | _pending_ |
| LLM-judge faithfulness (1–5) | _pending_ |
| Latency mean / p90 | _pending_ |
