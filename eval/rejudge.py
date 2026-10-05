"""Re-judge saved agent-eval replies with ONE judge model, so runs are comparable.

`run_eval agent --judge` uses AI_MODEL as the judge, i.e. usually the same model that
wrote the replies (self-judging inflates scores). This re-scores saved result files
offline with whatever AI_MODEL is set now (chat/completions endpoint).

    AI_MODEL=deepseek-v4.1-flash python -m eval.rejudge eval/results/A.json eval/results/B.json
"""
from __future__ import annotations

import json
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor

import yaml

from eval import run_eval as E
from retrieval import config
from retrieval.langid import detect_language

CASES = {c["id"]: c for c in yaml.safe_load((E.ROOT / "safety_cases.yaml").read_text(encoding="utf-8"))["cases"]}


def _one(row: dict):
    if not row.get("reply") or row.get("status") not in ("ok", "unverified"):
        return None
    case = CASES[row["id"]]
    question = case["messages"][-1]["text"]
    lang = case.get("expect", {}).get("lang") or detect_language(question)[0]
    texts = []
    for cid in row["citations"]:
        v = E._resolve_citation(cid, lang)
        if v is None:
            continue
        texts.append(v.text_ar + ("\n" + v.translation if getattr(v, "translation", None) else "")
                     if hasattr(v, "text_ar") else v["text_ar"])
    return row["id"], E._judge(question, row["reply"], texts)


def main(paths: list[str]) -> None:
    print(f"judge: {config.AI_MODEL}\n")
    for path in paths:
        rows = json.load(open(path, encoding="utf-8"))["rows"]
        with ThreadPoolExecutor(6) as ex:
            res = [x for x in ex.map(_one, rows) if x]
        ok = [j for _, j in res if "faithfulness" in j]
        print(f"{path}: n={len(ok)} faithfulness={statistics.mean(j['faithfulness'] for j in ok):.2f} "
              f"grounded={sum(bool(j.get('grounded')) for j in ok) / len(ok):.0%}")
        for cid, j in res:
            if not j.get("grounded"):
                print(f"  - {cid}: {'; '.join(j.get('issues', []))[:300]}")


if __name__ == "__main__":
    main(sys.argv[1:])
