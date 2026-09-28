# Retrieval evaluation (2026-09-28)

Index: {'qa': 1116, 'quran': 6236} · k = 6 · 41 answerable + 11 unanswerable questions

## Summary

| reranker | queries | Recall@6 | MRR | latency ms (mean / p90) | best threshold | answerable but abstained | unanswerable correctly abstained |
|---|---|---|---|---|---|---|---|
| minilm | raw | 93% | 0.83 | 858 / 1173 | 0.20 | 5% | 100% |
| minilm | analyzed | 98% | 0.93 | 1667 / 1932 | 0.30 | 2% | 100% |

*raw* = only the seeker's words; *analyzed* = plus one Arabic reformulation, as the agent's analyzer produces. Latency is per retrieve() call on this machine's CPU.

### minilm/raw

Missed (3): `black_stone_hostile` (got Q:37:94, Q:56:43, Q:77:48), `apostasy` (got Q:60:9, Q:3:85, Q:6:125), `mercy_prophet` (got Q:15:49, Q:42:48, Q:57:9)

Unanswerable top scores: `fake_hadith_computer` 0.03, `capital_france` 0.01, `cake_recipe` 0.07, `world_cup` 0.20, `gaming_laptop` 0.05, `quantum` 0.02, `kabsa_ar` 0.05, `stock_price_ar` 0.00, `weather_ur` 0.04, `smartphones_verse` 0.02, `bitcoin_hadith` 0.01

| threshold | answerable but abstained | unanswerable correctly abstained |
|---|---|---|
| 0.20 | 5% | 100% |
| 0.25 | 5% | 100% |
| 0.30 | 10% | 100% |
| 0.35 | 12% | 100% |
| 0.40 | 12% | 100% |
| 0.45 | 12% | 100% |
| 0.50 | 12% | 100% |
| 0.55 | 17% | 100% |
| 0.60 | 20% | 100% |
| 0.65 | 24% | 100% |
| 0.70 | 24% | 100% |
| 0.75 | 27% | 100% |
| 0.80 | 29% | 100% |

### minilm/analyzed

Missed (1): `tawhid_beginner` (got Q:21:92, Q:53:51, Q:10:105)

Unanswerable top scores: `fake_hadith_computer` 0.26, `capital_france` 0.01, `cake_recipe` 0.18, `world_cup` 0.20, `gaming_laptop` 0.21, `quantum` 0.06, `kabsa_ar` 0.20, `stock_price_ar` 0.00, `weather_ur` 0.27, `smartphones_verse` 0.04, `bitcoin_hadith` 0.22

| threshold | answerable but abstained | unanswerable correctly abstained |
|---|---|---|
| 0.20 | 2% | 64% |
| 0.25 | 2% | 82% |
| 0.30 | 2% | 100% |
| 0.35 | 2% | 100% |
| 0.40 | 2% | 100% |
| 0.45 | 2% | 100% |
| 0.50 | 2% | 100% |
| 0.55 | 2% | 100% |
| 0.60 | 2% | 100% |
| 0.65 | 2% | 100% |
| 0.70 | 5% | 100% |
| 0.75 | 5% | 100% |
| 0.80 | 5% | 100% |
