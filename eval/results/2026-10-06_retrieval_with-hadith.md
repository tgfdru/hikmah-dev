# Retrieval evaluation (2026-10-06)

Index: {'qa': 1116, 'hadith': 3573, 'quran': 6236, 'dawah': 6766} · k = 6 · 46 answerable + 11 unanswerable questions

## Summary

| reranker | queries | Recall@6 | MRR | latency ms (mean / p90) | best threshold | answerable but abstained | unanswerable correctly abstained |
|---|---|---|---|---|---|---|---|
| minilm | raw | 85% | 0.72 | 1824 / 2233 | 0.20 | 9% | 100% |
| minilm | analyzed | 98% | 0.90 | 2831 / 3164 | 0.35 | 2% | 100% |

*raw* = only the seeker's words; *analyzed* = plus one Arabic reformulation, as the agent's analyzer produces. Latency is per retrieve() call on this machine's CPU.

### minilm/raw

Missed (7): `black_stone_hostile` (got Q:9:112, Q:37:94, Q:22:77), `quran_author` (got Q:39:41, QA:bayyinat:42, QA:bayyinat:42:2), `apostasy` (got H:hadeethenc:11220, Q:60:9, Q:3:85), `evolution` (got SH:38726:378, SH:1075:135, SH:38726:724), `mercy_prophet` (got Q:15:49, Q:42:48, Q:46:8), `hadith_intention` (got H:hadeethenc:65037, Q:47:20, Q:50:17), `hadith_mercy_people` (got Q:45:20, Q:10:57, Q:2:54)

Unanswerable top scores: `fake_hadith_computer` 0.05, `capital_france` 0.03, `cake_recipe` 0.07, `world_cup` 0.20, `gaming_laptop` 0.05, `quantum` 0.01, `kabsa_ar` 0.05, `stock_price_ar` 0.01, `weather_ur` 0.02, `smartphones_verse` 0.02, `bitcoin_hadith` 0.04

| threshold | answerable but abstained | unanswerable correctly abstained |
|---|---|---|
| 0.20 | 9% | 100% |
| 0.25 | 9% | 100% |
| 0.30 | 11% | 100% |
| 0.35 | 15% | 100% |
| 0.40 | 15% | 100% |
| 0.45 | 15% | 100% |
| 0.50 | 17% | 100% |
| 0.55 | 26% | 100% |
| 0.60 | 26% | 100% |
| 0.65 | 28% | 100% |
| 0.70 | 33% | 100% |
| 0.75 | 35% | 100% |
| 0.80 | 35% | 100% |

### minilm/analyzed

Missed (1): `tawhid_beginner` (got SH:95570:174, SH:38726:372, SH:95570:163)

Unanswerable top scores: `fake_hadith_computer` 0.35, `capital_france` 0.01, `cake_recipe` 0.21, `world_cup` 0.20, `gaming_laptop` 0.21, `quantum` 0.03, `kabsa_ar` 0.20, `stock_price_ar` 0.01, `weather_ur` 0.27, `smartphones_verse` 0.04, `bitcoin_hadith` 0.30

| threshold | answerable but abstained | unanswerable correctly abstained |
|---|---|---|
| 0.20 | 0% | 55% |
| 0.25 | 2% | 73% |
| 0.30 | 2% | 82% |
| 0.35 | 2% | 100% |
| 0.40 | 2% | 100% |
| 0.45 | 4% | 100% |
| 0.50 | 7% | 100% |
| 0.55 | 7% | 100% |
| 0.60 | 7% | 100% |
| 0.65 | 7% | 100% |
| 0.70 | 9% | 100% |
| 0.75 | 9% | 100% |
| 0.80 | 11% | 100% |
