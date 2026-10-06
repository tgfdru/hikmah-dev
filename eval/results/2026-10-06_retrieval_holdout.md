# Retrieval evaluation (2026-10-06)

Index: {'qa': 1116, 'quran': 6236, 'dawah': 6766} · k = 6 · 10 answerable + 10 unanswerable questions

## Summary

| reranker | queries | Recall@6 | MRR | latency ms (mean / p90) | best threshold | answerable but abstained | unanswerable correctly abstained |
|---|---|---|---|---|---|---|---|
| minilm | raw | 80% | 0.64 | 1242 / 1663 | 0.30 | 10% | 90% |
| minilm | analyzed | 100% | 0.88 | 2461 / 2753 | 0.35 | 0% | 100% |

*raw* = only the seeker's words; *analyzed* = plus one Arabic reformulation, as the agent's analyzer produces. Latency is per retrieve() call on this machine's CPU.

### minilm/raw

Missed (2): `quran_word` (got Q:13:1, Q:7:158, Q:4:174), `forced` (got Q:2:131, QA:bayyinat:65:3, Q:27:31)

Unanswerable top scores: `computer_hadith_v2` 0.03, `airplanes` 0.13, `dinosaurs` 0.76, `phones` 0.01, `internet_ar` 0.25, `pasta` 0.08, `electric_cars` 0.01, `messi` 0.03, `netflix` 0.01, `coffee_hadith` 0.06

| threshold | answerable but abstained | unanswerable correctly abstained |
|---|---|---|
| 0.20 | 10% | 80% |
| 0.25 | 10% | 80% |
| 0.30 | 10% | 90% |
| 0.35 | 10% | 90% |
| 0.40 | 20% | 90% |
| 0.45 | 20% | 90% |
| 0.50 | 20% | 90% |
| 0.55 | 20% | 90% |
| 0.60 | 30% | 90% |
| 0.65 | 40% | 90% |
| 0.70 | 40% | 90% |
| 0.75 | 40% | 90% |
| 0.80 | 40% | 100% |

### minilm/analyzed

Missed (0): none

Unanswerable top scores: `computer_hadith_v2` 0.34, `airplanes` 0.22, `dinosaurs` 0.20, `phones` 0.04, `internet_ar` 0.25, `pasta` 0.09, `electric_cars` 0.01, `messi` 0.00, `netflix` 0.07, `coffee_hadith` 0.11

| threshold | answerable but abstained | unanswerable correctly abstained |
|---|---|---|
| 0.20 | 0% | 70% |
| 0.25 | 0% | 80% |
| 0.30 | 0% | 90% |
| 0.35 | 0% | 100% |
| 0.40 | 10% | 100% |
| 0.45 | 10% | 100% |
| 0.50 | 10% | 100% |
| 0.55 | 10% | 100% |
| 0.60 | 10% | 100% |
| 0.65 | 10% | 100% |
| 0.70 | 10% | 100% |
| 0.75 | 10% | 100% |
| 0.80 | 10% | 100% |
