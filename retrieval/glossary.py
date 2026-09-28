"""Approved term equivalents for the prompt (data/glossary.json).

    terms = glossary_for([conversation_text, *[e.text_ar for e in evidence]], lang="en")
    prompt_block = format_for_prompt(terms, lang="en")

Only terms that actually occur in the given texts are returned, so the prompt stays
small. Official challenge terms come first and carry a usage rule.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache

from retrieval import config
from retrieval.normalize_ar import norm


def _key(text: str) -> str:
    return re.sub(r"[^ء-ي ]", " ", norm(text))


@lru_cache(maxsize=1)
def load_glossary() -> list[dict]:
    if not config.GLOSSARY_PATH.exists():
        return []
    data = json.loads(config.GLOSSARY_PATH.read_text(encoding="utf-8"))
    return data.get("terms", [])


def _english_names(term: dict) -> list[str]:
    names = []
    for field in ("en", "jamhara_en"):
        for part in re.split(r"[/،,()]", term.get(field) or ""):
            part = part.strip().lower().replace("‘", "'").replace("’", "'")
            if len(part) >= 4:
                names.append(part)
    return names


def glossary_for(texts: list[str], lang: str = "en", limit: int = 15) -> list[dict]:
    """Glossary entries whose Arabic or English form appears in any of `texts`."""
    ar_blob = " " + " ".join(_key(t) for t in texts) + " "
    en_blob = " ".join(texts).lower().replace("‘", "'").replace("’", "'")
    hits = []
    for term in load_glossary():
        k = _key(term["ar"]).strip()
        bare = k[2:] if k.startswith("ال") and len(k) > 4 else k
        found = f" {k} " in ar_blob or (bare != k and re.search(rf"[\s](?:[وفبلك]|ال|وال|بال|لل)?{re.escape(bare)}[\s]", ar_blob))
        if not found:
            found = any(re.search(rf"\b{re.escape(n)}\b", en_blob) for n in _english_names(term))
        if found:
            hits.append(term)
    hits.sort(key=lambda t: t["status"] != "official_challenge")
    return hits[:limit]


def format_for_prompt(terms: list[dict], lang: str = "en") -> str:
    """One line per term: Arabic -> approved equivalent [usage rule / definition]."""
    lines = []
    for t in terms:
        equivalent = t.get(lang) or t.get(f"jamhara_{lang}") or t.get("en") or t.get("jamhara_en") or ""
        note = t.get("usage_rule_ar") or t.get(f"definition_{lang}") or t.get("definition_en") or ""
        lines.append(f"- {t['ar']} → {equivalent}" + (f" — {note}" if note else ""))
    return "\n".join(lines)
