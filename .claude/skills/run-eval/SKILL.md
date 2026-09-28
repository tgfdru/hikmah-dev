---
name: run-eval
description: Run Mu'een's evaluations (retrieval quality and abstain threshold, misquote detection, and the 41 end-to-end safety cases against the /suggest API) and update docs/EVALUATION.md. Use after changing prompts, thresholds, retrieval code or sources, or when asked for metrics.
---

1. Make sure the index exists: `python -m ingest.build_all` (fast when cached).
2. Knowledge layer: `python -m eval.run_eval retrieval --rerankers none` (add
   `minilm,bge` for the full comparison; `bge` is slow on CPU) and
   `python -m eval.run_eval ayah`.
3. Full pipeline: start the API (`uvicorn api.main:app --port 8000`), then
   `python -m eval.run_eval agent --api http://localhost:8000 --judge`
   (`--only id1,id2` for a subset; `--api-key` if the API requires `X-API-Key`).
   The judge uses `AI_API_KEY` / `AI_MODEL`.
4. Results land in `eval/results/<date>_<name>.md|json`. Copy the summary tables into
   `docs/EVALUATION.md`, with the date, the model and the reranker used.
5. Report failures honestly: list failed case ids and the failed checks; do not
   edit `eval/*.yaml` expectations to make a failing case pass unless the
   expectation itself was wrong (explain why in the commit message).
