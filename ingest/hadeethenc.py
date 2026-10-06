"""HadeethEnc (the Encyclopedia of Translated Prophetic Hadiths) -> verbatim hadith store.

    python -m ingest.hadeethenc            # download (cached), build store + hadeethenc.jsonl

Source: hadeethenc.com, the challenge organiser's own encyclopedia (named in the updated
reference pack). Every hadith comes with its grade, attribution, an official explanation and
approved translations, so hadith get the same treatment as the Quran: the exact text lives in
a store (WORK_DIR/store/hadith.sqlite) and `get_verbatim("H:hadeethenc:<id>", lang)` is the
only way it reaches a reply.

Only hadith graded authentic or good (صحيح / حسن, including "لغيره") are kept. Raw API
answers are cached under WORK_DIR/raw/hadeethenc/<lang>/<id>.json, so a rebuild needs no
network. The text is never committed to git (same rule as every source).
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from retrieval import config

API = "https://hadeethenc.com/api/v1"
PAGE_URL = "https://hadeethenc.com/{lang}/browse/hadith/{id}"
LANGS = ("ar", "en", "ur", "id", "fr")  # the agent's reply languages; ar is the source text
RAW = config.RAW_DIR / "hadeethenc"
HEADERS = {"User-Agent": "MueenKnowledgeBuilder/1.0 (+https://sheykak.com; hackathon research use)"}
WORKERS = 4  # polite: a few requests at a time
SOURCE_AR = "موسوعة الأحاديث النبوية المترجمة (HadeethEnc)"
KEEP_GRADES = ("صحيح", "حسن")  # also matches "صحيح لغيره", "حسن صحيح" ...


def _get_json(client: httpx.Client, url: str, params: dict) -> dict | list:
    for attempt in range(5):
        try:
            r = client.get(url, params=params, timeout=60)
            if r.status_code == 404:  # e.g. no translation in this language: final, no retry
                r.raise_for_status()
            if r.status_code == 429 or r.status_code >= 500:
                raise httpx.HTTPStatusError("retry", request=r.request, response=r)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            if attempt == 4 or (isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404):
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def hadith_ids(client: httpx.Client) -> list[str]:
    """Every hadith id, collected from the root categories (a hadith can sit in several)."""
    roots = [c for c in _get_json(client, f"{API}/categories/roots/", {"language": "ar"})]
    ids: dict[str, None] = {}
    for c in roots:
        page, last = 1, 1
        while page <= last:
            d = _get_json(client, f"{API}/hadeeths/list/",
                          {"language": "ar", "category_id": c["id"], "page": page, "per_page": 100})
            ids.update((h["id"], None) for h in d["data"])
            last = int(d["meta"]["last_page"])
            page += 1
    return list(ids)


def download(refresh: bool = False) -> list[str]:
    RAW.mkdir(parents=True, exist_ok=True)
    ids_file = RAW / "ids.json"
    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        if refresh or not ids_file.exists():
            ids_file.write_text(json.dumps(hadith_ids(client)), encoding="utf-8")
        ids = json.loads(ids_file.read_text(encoding="utf-8"))

        def todo(lang: str) -> list[tuple[str, str]]:
            jobs = [(lang, i) for i in ids if refresh or not (RAW / lang / f"{i}.json").exists()]
            if lang != "ar":  # only the languages HadeethEnc lists for that hadith
                jobs = [(l, i) for l, i in jobs if lang in (_load("ar", i).get("translations") or [])]
            return jobs

        def fetch(job: tuple[str, str]) -> None:
            lang, i = job
            dest = RAW / lang / f"{i}.json"
            dest.parent.mkdir(exist_ok=True)
            try:
                d = _get_json(client, f"{API}/hadeeths/one/", {"language": lang, "id": i})
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:  # not translated into this language
                    d = {}
                else:
                    raise
            dest.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

        for lang in LANGS:  # Arabic first: it lists the available translations
            jobs = todo(lang)
            print(f"  HadeethEnc: {len(ids)} hadith, {len(jobs)} {lang} pages to fetch", flush=True)
            with ThreadPoolExecutor(WORKERS) as pool:
                for n, _ in enumerate(pool.map(fetch, jobs), 1):
                    if n % 1000 == 0:
                        print(f"    {lang} {n}/{len(jobs)}", flush=True)
    return ids


def _load(lang: str, i: str) -> dict:
    p = RAW / lang / f"{i}.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text(encoding="utf-8"))
    return d if isinstance(d, dict) and d.get("id") else {}


def build(refresh: bool = False) -> None:
    ids = download(refresh)
    rows, records, skipped = [], [], {}
    for i in ids:
        ar = _load("ar", i)
        grade = (ar.get("grade") or "").strip()
        if not ar.get("hadeeth") or not any(g in grade for g in KEEP_GRADES):
            skipped[grade or "(none)"] = skipped.get(grade or "(none)", 0) + 1
            continue
        tr = {}
        for lang in LANGS[1:]:
            d = _load(lang, i)
            if d.get("hadeeth"):
                tr[lang] = {k: d.get(k) for k in ("title", "hadeeth", "attribution", "grade", "explanation")}
        rows.append((i, ar["title"], ar["hadeeth"], ar.get("attribution") or "", grade,
                     ar.get("explanation") or "", ar.get("reference") or "",
                     json.dumps(tr, ensure_ascii=False), PAGE_URL.format(lang="ar", id=i)))
        records.append({
            "id": f"H:hadeethenc:{i}", "type": "hadith", "title": ar["title"],
            "text_ar": ar["hadeeth"], "translations": {k: v["hadeeth"] for k, v in tr.items()},
            "explanation_ar": ar.get("explanation") or "",
            "source": SOURCE_AR, "ref": ar.get("attribution") or "", "grade": grade,
            "source_url": PAGE_URL.format(lang="ar", id=i),
        })

    config.STORE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = config.HADITH_DB.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    db.executescript("""
        CREATE TABLE hadith (id TEXT PRIMARY KEY, title_ar TEXT, text_ar TEXT NOT NULL,
                             attribution_ar TEXT, grade_ar TEXT NOT NULL, explanation_ar TEXT,
                             reference_ar TEXT, translations TEXT NOT NULL, url TEXT NOT NULL);
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
    """)
    db.executemany("INSERT INTO hadith VALUES (?,?,?,?,?,?,?,?,?)", rows)
    db.executemany("INSERT INTO meta VALUES (?,?)", [
        ("source", "hadeethenc.com API v1"), ("retrieved", time.strftime("%Y-%m-%d")),
        ("count", str(len(rows))), ("languages", ",".join(LANGS)),
    ])
    db.commit()
    db.close()
    tmp.replace(config.HADITH_DB)

    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out = config.PROCESSED_DIR / "hadeethenc.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"HadeethEnc: {len(rows)} hadith kept -> {config.HADITH_DB.name}, {out.name}; skipped {skipped}")


if __name__ == "__main__":
    build(refresh="--refresh" in sys.argv)
