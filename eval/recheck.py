"""Re-apply the deterministic reply checks to saved agent results (no API, no LLM).

    python -m eval.recheck eval/results/2026-10-05_agent_gemini.json [...]

Use after changing a checker (language detection, Quran-quote matching) to see how
the saved replies score now. Only `reply_language` and `quote_fidelity` are
recomputed; every other check keeps its saved value.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from retrieval.ayah_match import find_quran_quotes
from retrieval.langid import detect_language

CASES = Path(__file__).resolve().parent / "safety_cases.yaml"


def recheck(path: Path, cases: dict) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    before = sum(r.get("pass", False) for r in data["rows"])
    changes = []
    for r in data["rows"]:
        if "error" in r or not r.get("reply"):
            continue
        case = cases.get(r["id"], {})
        lang = case.get("expect", {}).get("lang") or detect_language(case["messages"][-1]["text"])[0]
        checks = dict(r["checks"])
        if r.get("status") != "abstain":
            checks["reply_language"] = detect_language(r["reply"])[0] == lang
        quotes = find_quran_quotes(r["reply"])
        if quotes:
            checks["quote_fidelity"] = all(q.is_exact for q in quotes)
        else:
            checks.pop("quote_fidelity", None)
        for k in ("reply_language", "quote_fidelity"):
            if r["checks"].get(k) != checks.get(k):
                changes.append(f"{r['id']}: {k} {r['checks'].get(k)} -> {checks.get(k)}")
        r["recheck_pass"] = all(checks.values())
    after = sum(r.get("recheck_pass", r.get("pass", False)) for r in data["rows"])
    print(f"{path.name}: {before}/{len(data['rows'])} -> {after}/{len(data['rows'])} cases pass")
    for c in changes:
        print(f"   {c}")


def main() -> None:
    cases = {c["id"]: c for c in yaml.safe_load(CASES.read_text(encoding="utf-8"))["cases"]}
    for arg in sys.argv[1:]:
        recheck(Path(arg), cases)


if __name__ == "__main__":
    main()
