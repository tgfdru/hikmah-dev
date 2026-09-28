"""Optional live hadith search through Dorar's public API (dorar.net).  OFF BY DEFAULT.

Status: UNTESTED against the live service. dorar.net answers cloud/datacenter IPs
with a Cloudflare 403, so it could not be reached from the development machine.
Test it from a normal connection before enabling:

    python -m retrieval.dorar "إنما الأعمال بالنيات"

Enable with DORAR_ENABLED=1. Design:
  * Arabic queries only (Dorar searches Arabic text); at most 2 per call; short timeout.
  * Only hadith graded authentic are kept (Sahih al-Bukhari / Sahih Muslim, or a
    grade containing "صحيح" with no weakening word) - the challenge requires
    "no hadith without a source and an approved grade".
  * Every hadith returned is cached in SQLite so `get_verbatim("H:...")` resolves it
    later with exactly the text Dorar returned - the agent's verifier then treats
    hadith placeholders the same way as Quran ones. Nothing is invented or edited.
  * Any network/parse failure returns [] (the agent then simply has no hadith).
"""
from __future__ import annotations

import hashlib
import html
import re
import sqlite3
import sys
import threading
import time
from urllib.parse import quote

import httpx

from retrieval import config
from retrieval.contract import Evidence
from retrieval.normalize_ar import has_arabic, strip_diacritics

API_URL = "https://dorar.net/dorar_api.json"
SEARCH_URL = "https://dorar.net/hadith/search?q="
USER_AGENT = "Mozilla/5.0 (compatible; MueenDaiAssistant/1.0; +https://sheykak.com)"
CACHE_DB = config.CACHE_DIR / "hadith.sqlite"

SAHIHAYN = {"صحيح البخاري": "bukhari", "صحيح مسلم": "muslim"}
_NEGATIVE = re.compile("ضعيف|موضوع|منكر|لا يصح|باطل|لا أصل|كذب|شاذ|مرسل|منقطع|معلول|واه")
_FIELDS = {
    "narrator": "الراوي",
    "muhaddith": "المحدث",
    "source": "المصدر",
    "number": "الصفحة أو الرقم",
    "grade": "خلاصة حكم المحدث",
}
_lock = threading.Lock()


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def parse_results(result_html: str) -> list[dict]:
    """Parse the HTML fragment inside Dorar's JSON answer into hadith dicts."""
    items = []
    blocks = re.split(r'<div[^>]*class="hadith"[^>]*>', result_html)[1:]
    for block in blocks:
        text_part, _, info_part = block.partition('class="hadith-info"')
        text = _text(text_part.split("</div>")[0])
        text = re.sub(r"^\d+\s*-\s*", "", text)  # leading result number "1 - "
        info = _text(info_part)
        fields = {}
        labels = "|".join(map(re.escape, _FIELDS.values()))
        for key, label in _FIELDS.items():
            m = re.search(rf"{re.escape(label)}\s*:\s*(.*?)(?=(?:{labels})\s*:|$)", info)
            fields[key] = m.group(1).strip(" -|") if m else ""
        if text:
            items.append({"text_ar": text, **fields})
    return items


def is_authentic(h: dict) -> bool:
    grade = h.get("grade", "")
    if h.get("source", "") in SAHIHAYN and not _NEGATIVE.search(grade):
        return True
    return "صحيح" in grade and not _NEGATIVE.search(grade)


def hadith_id(h: dict) -> str:
    slug = SAHIHAYN.get(h.get("source", "").strip())
    num = re.sub(r"\D", "", h.get("number", ""))
    if slug and num:
        return f"H:{slug}:{num}"
    digest = hashlib.sha1(strip_diacritics(h["text_ar"]).encode()).hexdigest()[:10]
    return f"H:dorar:{digest}"


def _db() -> sqlite3.Connection:
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CACHE_DB, timeout=10)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS hadith (id TEXT PRIMARY KEY, text_ar TEXT, source TEXT, ref TEXT,"
        " grade TEXT, narrator TEXT, muhaddith TEXT, url TEXT, fetched_at REAL)"
    )
    return conn


def _to_evidence(row: dict, score: float) -> Evidence:
    return Evidence(
        id=row["id"], type="hadith", text_ar=row["text_ar"], translation=None,
        source=row["source"] or "الدرر السنية", ref=row["ref"], grade=row["grade"] or None,
        source_url=row["url"], score=round(score, 4),
    )


def fetch(query: str) -> list[dict]:
    """Raw authentic hadith for one Arabic query (cached). [] on any failure."""
    try:
        r = httpx.get(API_URL, params={"skey": query}, timeout=config.DORAR_TIMEOUT,
                      headers={"User-Agent": USER_AGENT}, follow_redirects=True)
        r.raise_for_status()
        result_html = r.json().get("ahadith", {}).get("result", "")
    except (httpx.HTTPError, ValueError, AttributeError) as exc:
        print(f"dorar: request failed ({exc.__class__.__name__}: {exc})", file=sys.stderr)
        return []
    rows = []
    for h in parse_results(result_html):
        if not is_authentic(h):
            continue
        ref = " - ".join(x for x in [h.get("source"), h.get("number") and f"رقم {h['number']}"] if x)
        row = {
            "id": hadith_id(h), "text_ar": h["text_ar"], "source": h.get("source", ""),
            "ref": ref or "الدرر السنية", "grade": h.get("grade", ""), "narrator": h.get("narrator", ""),
            "muhaddith": h.get("muhaddith", ""), "url": SEARCH_URL + quote(query),
        }
        rows.append(row)
    if rows:
        with _lock, _db() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO hadith VALUES (:id,:text_ar,:source,:ref,:grade,:narrator,"
                ":muhaddith,:url,:t)", [{**r, "t": time.time()} for r in rows],
            )
    return rows


def search(queries: list[str], lang: str, scorer=None, limit: int = 3) -> list[Evidence]:
    """Authentic hadith for the Arabic queries, scored on the same 0-1 scale as other evidence."""
    arabic = [strip_diacritics(q) for q in queries if has_arabic(q)][:2]
    rows: dict[str, dict] = {}
    for q in arabic:
        for row in fetch(q):
            rows.setdefault(row["id"], row)
    if not rows:
        return []
    items = list(rows.values())
    scores = scorer(queries, [r["text_ar"] for r in items]) if scorer else [0.5] * len(items)
    ranked = sorted(zip(items, scores), key=lambda x: x[1], reverse=True)[:limit]
    return [_to_evidence(r, s) for r, s in ranked]


def get_cached(ref_id: str, lang: str) -> Evidence | None:
    """Exact text of a hadith previously returned by Dorar, or None."""
    if not CACHE_DB.exists():
        return None
    with _db() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM hadith WHERE id=?", (ref_id,)).fetchone()
    return _to_evidence(dict(row), 1.0) if row else None


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "إنما الأعمال بالنيات"
    print(f"Querying Dorar for: {q}")
    found = fetch(q)
    print(f"{len(found)} authentic hadith")
    for row in found[:5]:
        print("-", row["id"], "|", row["source"], "|", row["grade"], "|", row["text_ar"][:120])
