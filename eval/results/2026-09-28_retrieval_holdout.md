# Retrieval evaluation (2026-09-28)

Index: {'qa': 1116, 'quran': 6236} · k = 6 · 10 answerable + 10 unanswerable questions

## Summary

| reranker | queries | Recall@6 | MRR | latency ms (mean / p90) | best threshold | answerable but abstained | unanswerable correctly abstained |
|---|---|---|---|---|---|---|---|
| minilm | raw | 80% | 0.72 | 817 / 1055 | 0.20 | 10% | 100% |
| minilm | analyzed | 100% | 1.00 | 1600 / 1981 | 0.35 | 0% | 100% |
| none | raw | 70% | 0.65 | 253 / 285 | 0.55 | 0% | 50% |
| none | analyzed | 100% | 1.00 | 438 / 554 | 0.60 | 0% | 90% |

*raw* = only the seeker's words; *analyzed* = plus one Arabic reformulation, as the agent's analyzer produces. Latency is per retrieve() call on this machine's CPU.

### minilm/raw

Missed (2): `quran_word` (got Q:13:1, Q:81:19, Q:4:174), `forced` (got Q:2:131, QA:bayyinat:65:3, Q:27:31)

Unanswerable top scores: `computer_hadith_v2` 0.05, `airplanes` 0.13, `dinosaurs` 0.16, `phones` 0.01, `internet_ar` 0.14, `pasta` 0.02, `electric_cars` 0.01, `messi` 0.00, `netflix` 0.01, `coffee_hadith` 0.05

| threshold | answerable but abstained | unanswerable correctly abstained |
|---|---|---|
| 0.20 | 10% | 100% |
| 0.25 | 10% | 100% |
| 0.30 | 10% | 100% |
| 0.35 | 10% | 100% |
| 0.40 | 20% | 100% |
| 0.45 | 20% | 100% |
| 0.50 | 20% | 100% |
| 0.55 | 20% | 100% |
| 0.60 | 30% | 100% |
| 0.65 | 40% | 100% |
| 0.70 | 40% | 100% |
| 0.75 | 40% | 100% |
| 0.80 | 50% | 100% |

### minilm/analyzed

Missed (0): none

Unanswerable top scores: `computer_hadith_v2` 0.33, `airplanes` 0.22, `dinosaurs` 0.20, `phones` 0.04, `internet_ar` 0.14, `pasta` 0.09, `electric_cars` 0.01, `messi` 0.04, `netflix` 0.07, `coffee_hadith` 0.11

| threshold | answerable but abstained | unanswerable correctly abstained |
|---|---|---|
| 0.20 | 0% | 80% |
| 0.25 | 0% | 90% |
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

### none/raw

Missed (3): `quran_word` (got Q:2:252, Q:4:174, Q:16:102), `forced` (got Q:39:12, Q:68:35, Q:6:125), `after_death` (got Q:57:17, Q:3:85, Q:39:42)

Unanswerable top scores: `computer_hadith_v2` 0.57, `airplanes` 0.60, `dinosaurs` 0.50, `phones` 0.58, `internet_ar` 0.53, `pasta` 0.56, `electric_cars` 0.57, `messi` 0.38, `netflix` 0.47, `coffee_hadith` 0.50

| threshold | answerable but abstained | unanswerable correctly abstained |
|---|---|---|
| 0.20 | 0% | 0% |
| 0.25 | 0% | 0% |
| 0.30 | 0% | 0% |
| 0.35 | 0% | 0% |
| 0.40 | 0% | 10% |
| 0.45 | 0% | 10% |
| 0.50 | 0% | 30% |
| 0.55 | 0% | 50% |
| 0.60 | 40% | 90% |
| 0.65 | 100% | 100% |
| 0.70 | 100% | 100% |
| 0.75 | 100% | 100% |
| 0.80 | 100% | 100% |

### none/analyzed

Missed (0): none

Unanswerable top scores: `computer_hadith_v2` 0.58, `airplanes` 0.64, `dinosaurs` 0.56, `phones` 0.58, `internet_ar` 0.57, `pasta` 0.56, `electric_cars` 0.57, `messi` 0.38, `netflix` 0.47, `coffee_hadith` 0.56

| threshold | answerable but abstained | unanswerable correctly abstained |
|---|---|---|
| 0.20 | 0% | 0% |
| 0.25 | 0% | 0% |
| 0.30 | 0% | 0% |
| 0.35 | 0% | 0% |
| 0.40 | 0% | 10% |
| 0.45 | 0% | 10% |
| 0.50 | 0% | 20% |
| 0.55 | 0% | 20% |
| 0.60 | 0% | 90% |
| 0.65 | 30% | 100% |
| 0.70 | 80% | 100% |
| 0.75 | 90% | 100% |
| 0.80 | 100% | 100% |
