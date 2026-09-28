# Retrieval evaluation (2026-09-28)

Index: {'qa': 1116, 'quran': 6236} · k = 6 · 41 answerable + 11 unanswerable questions

## Summary

| reranker | queries | Recall@6 | MRR | latency ms (mean / p90) | best threshold | answerable but abstained | unanswerable correctly abstained |
|---|---|---|---|---|---|---|---|
| none | raw | 93% | 0.79 | 271 / 356 | 0.60 | 34% | 100% |
| none | analyzed | 98% | 0.93 | 416 / 470 | 0.60 | 2% | 91% |
| minilm | raw | 93% | 0.83 | 862 / 1085 | 0.20 | 5% | 100% |
| minilm | analyzed | 98% | 0.89 | 1090 / 1287 | 0.20 | 5% | 100% |
| bge | raw | 93% | 0.87 | 6671 / 8279 | 0.10 | 15% | 100% |
| bge | analyzed | 98% | 0.92 | 7508 / 8328 | 0.10 | 12% | 100% |

*raw* = only the seeker's words; *analyzed* = plus one Arabic reformulation, as the agent's analyzer produces. Latency is per retrieve() call on this machine's CPU.

### none/raw

Missed (3): `black_stone_hostile` (got Q:53:62, Q:37:161, Q:41:6), `apostasy` (got Q:60:9, Q:4:14, Q:5:33), `mercy_prophet` (got Q:17:87, Q:19:51, Q:44:42)

Unanswerable top scores: `fake_hadith_computer` 0.59, `capital_france` 0.37, `cake_recipe` 0.43, `world_cup` 0.44, `gaming_laptop` 0.38, `quantum` 0.48, `kabsa_ar` 0.52, `stock_price_ar` 0.42, `weather_ur` 0.58, `smartphones_verse` 0.53, `bitcoin_hadith` 0.57

| threshold | answerable but abstained | unanswerable correctly abstained |
|---|---|---|
| 0.20 | 0% | 0% |
| 0.25 | 0% | 0% |
| 0.30 | 0% | 0% |
| 0.35 | 0% | 0% |
| 0.40 | 0% | 18% |
| 0.45 | 0% | 45% |
| 0.50 | 2% | 55% |
| 0.55 | 10% | 73% |
| 0.60 | 34% | 100% |
| 0.65 | 66% | 100% |
| 0.70 | 93% | 100% |
| 0.75 | 98% | 100% |
| 0.80 | 100% | 100% |

### none/analyzed

Missed (1): `mercy_prophet` (got Q:17:87, Q:44:6, Q:44:42)

Unanswerable top scores: `fake_hadith_computer` 0.59, `capital_france` 0.37, `cake_recipe` 0.43, `world_cup` 0.44, `gaming_laptop` 0.39, `quantum` 0.48, `kabsa_ar` 0.52, `stock_price_ar` 0.42, `weather_ur` 0.60, `smartphones_verse` 0.56, `bitcoin_hadith` 0.57

| threshold | answerable but abstained | unanswerable correctly abstained |
|---|---|---|
| 0.20 | 0% | 0% |
| 0.25 | 0% | 0% |
| 0.30 | 0% | 0% |
| 0.35 | 0% | 0% |
| 0.40 | 0% | 18% |
| 0.45 | 0% | 45% |
| 0.50 | 0% | 55% |
| 0.55 | 2% | 64% |
| 0.60 | 2% | 91% |
| 0.65 | 15% | 100% |
| 0.70 | 39% | 100% |
| 0.75 | 51% | 100% |
| 0.80 | 93% | 100% |

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

Missed (1): `tawhid_beginner` (got Q:53:51, Q:11:95, Q:11:68)

Unanswerable top scores: `fake_hadith_computer` 0.05, `capital_france` 0.01, `cake_recipe` 0.18, `world_cup` 0.20, `gaming_laptop` 0.05, `quantum` 0.01, `kabsa_ar` 0.05, `stock_price_ar` 0.00, `weather_ur` 0.02, `smartphones_verse` 0.04, `bitcoin_hadith` 0.02

| threshold | answerable but abstained | unanswerable correctly abstained |
|---|---|---|
| 0.20 | 5% | 100% |
| 0.25 | 5% | 100% |
| 0.30 | 7% | 100% |
| 0.35 | 7% | 100% |
| 0.40 | 7% | 100% |
| 0.45 | 7% | 100% |
| 0.50 | 7% | 100% |
| 0.55 | 12% | 100% |
| 0.60 | 12% | 100% |
| 0.65 | 15% | 100% |
| 0.70 | 17% | 100% |
| 0.75 | 22% | 100% |
| 0.80 | 27% | 100% |

### bge/raw

Missed (3): `black_stone_hostile` (got Q:37:161, Q:37:94, Q:37:85), `apostasy` (got Q:3:85, Q:60:9, Q:6:125), `mercy_prophet` (got Q:58:12, Q:15:49, Q:57:9)

Unanswerable top scores: `fake_hadith_computer` 0.00, `capital_france` 0.00, `cake_recipe` 0.00, `world_cup` 0.00, `gaming_laptop` 0.00, `quantum` 0.00, `kabsa_ar` 0.00, `stock_price_ar` 0.00, `weather_ur` 0.00, `smartphones_verse` 0.01, `bitcoin_hadith` 0.02

| threshold | answerable but abstained | unanswerable correctly abstained |
|---|---|---|
| 0.20 | 20% | 100% |
| 0.25 | 20% | 100% |
| 0.30 | 20% | 100% |
| 0.35 | 20% | 100% |
| 0.40 | 20% | 100% |
| 0.45 | 20% | 100% |
| 0.50 | 27% | 100% |
| 0.55 | 27% | 100% |
| 0.60 | 32% | 100% |
| 0.65 | 34% | 100% |
| 0.70 | 34% | 100% |
| 0.75 | 41% | 100% |
| 0.80 | 44% | 100% |

### bge/analyzed

Missed (1): `tawhid_beginner` (got Q:12:108, Q:10:105, Q:46:30)

Unanswerable top scores: `fake_hadith_computer` 0.00, `capital_france` 0.08, `cake_recipe` 0.00, `world_cup` 0.00, `gaming_laptop` 0.00, `quantum` 0.00, `kabsa_ar` 0.00, `stock_price_ar` 0.00, `weather_ur` 0.00, `smartphones_verse` 0.00, `bitcoin_hadith` 0.01

| threshold | answerable but abstained | unanswerable correctly abstained |
|---|---|---|
| 0.20 | 20% | 100% |
| 0.25 | 22% | 100% |
| 0.30 | 22% | 100% |
| 0.35 | 22% | 100% |
| 0.40 | 22% | 100% |
| 0.45 | 22% | 100% |
| 0.50 | 29% | 100% |
| 0.55 | 29% | 100% |
| 0.60 | 32% | 100% |
| 0.65 | 34% | 100% |
| 0.70 | 34% | 100% |
| 0.75 | 37% | 100% |
| 0.80 | 39% | 100% |
