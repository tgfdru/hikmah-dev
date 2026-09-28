"""Build the Quran verbatim store (SQLite) and the Quran records for the index.

    python -m ingest.quran

Inputs  (data/raw/quranpedia/): mushafs-1.json.gz, surahs-index.json.gz,
        topics.json.gz, translation-<id>.json  (see ingest/download.py)
Outputs: data/store/verbatim.sqlite   - single source of truth for Quran text
         data/processed/quran.jsonl   - one record per ayah, for indexing
"""
from __future__ import annotations

import gzip
import html
import json
import re
import sqlite3
import unicodedata
from pathlib import Path

from retrieval import config
from retrieval.normalize_ar import norm
from retrieval.quran_meta import QURAN_SOURCE_AR, SURAH_NAMES_EN, quran_url

EXPECTED_AYAHS = 6236

_FOOTNOTE_SPLIT = re.compile(r"<br\s*/?>\s*_{5,}\s*<br\s*/?>", re.I)
_TAG = re.compile(r"<[^>]+>")
_LEADING_NUM = re.compile(r"^\s*\(?\d{1,3}\)?[.)]?\s+")
_NOTE_MARK = re.compile(r"\[\d{1,2}\]|\*+")


def _load_gz(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)["data"]


def clean_translation(raw: str) -> tuple[str, str | None]:
    """Split a Quranpedia translation into (text, footnotes) and strip markup."""
    parts = _FOOTNOTE_SPLIT.split(raw, maxsplit=1)
    main, notes = parts[0], (parts[1] if len(parts) > 1 else None)

    def tidy(s: str) -> str:
        s = html.unescape(_TAG.sub(" ", s))
        s = unicodedata.normalize("NFKC", s)  # also folds Arabic presentation forms
        return re.sub(r"\s+", " ", s).strip()

    main = _NOTE_MARK.sub("", tidy(main))
    main = _LEADING_NUM.sub("", main).strip()
    main = re.sub(r"\s+([,.;:!?،۔])", r"\1", main)
    return main, (tidy(notes) if notes else None)


def clean_ayah_text(text: str) -> str:
    return re.sub(r"[﻿​-‏]", "", text).strip()


def build(raw_dir: Path | None = None) -> None:
    raw_dir = raw_dir or config.RAW_DIR / "quranpedia"
    mushaf = _load_gz(raw_dir / f"mushafs-{config.QURAN_MUSHAF_ID}.json.gz")
    surah_index = {s["id"]: s for s in _load_gz(raw_dir / "surahs-index.json.gz")}
    topics = {
        (t["surah"], t["ayah"]): sorted({x["name"] for x in t["topics"]}
                                        | {x["parent"]["name"] for x in t["topics"] if x.get("parent")})
        for t in _load_gz(raw_dir / "topics.json.gz")
    }
    translations: dict[str, dict[tuple[int, int], tuple[str, str | None]]] = {}
    book_names: dict[str, str] = {}
    for lang, book_id in config.QURAN_TRANSLATIONS.items():
        book = json.loads((raw_dir / f"translation-{book_id}.json").read_text(encoding="utf-8"))
        book_names[lang] = book.get("short_name") or book.get("name") or str(book_id)
        translations[lang] = {
            (a["surah_number"], a["ayah_number"]): clean_translation(a["translated_text"] or "")
            for a in book["ayahs"]
        }
    manifest = json.loads((raw_dir / "manifest.json").read_text(encoding="utf-8"))

    config.STORE_DIR.mkdir(parents=True, exist_ok=True)
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    tmp_db = config.VERBATIM_DB.with_suffix(".tmp")
    tmp_db.unlink(missing_ok=True)
    db = sqlite3.connect(tmp_db)
    db.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE surahs (surah INTEGER PRIMARY KEY, name_ar TEXT, name_en TEXT,
                             ayah_count INTEGER, revelation TEXT);
        CREATE TABLE ayahs (surah INTEGER, ayah INTEGER, text_ar TEXT NOT NULL,
                            text_norm TEXT NOT NULL, page INTEGER, juz INTEGER,
                            PRIMARY KEY (surah, ayah));
        CREATE TABLE translations (surah INTEGER, ayah INTEGER, lang TEXT, text TEXT NOT NULL,
                                   notes TEXT, PRIMARY KEY (surah, ayah, lang));
        """
    )

    records = []
    count = 0
    for surah in mushaf["surahs"]:
        s = surah["id"]
        name_ar = surah["name"].replace("سورة", "").strip()
        info = surah_index.get(s, {})
        db.execute("INSERT INTO surahs VALUES (?,?,?,?,?)",
                   (s, name_ar, SURAH_NAMES_EN[s - 1], len(surah["ayahs"]), info.get("revelation_type")))
        for ayah in surah["ayahs"]:
            a = ayah["number"]
            text = clean_ayah_text(ayah["text"])
            db.execute("INSERT INTO ayahs VALUES (?,?,?,?,?,?)",
                       (s, a, text, norm(text), ayah.get("page_number"), ayah.get("juz")))
            tr = {}
            for lang, table in translations.items():
                if (s, a) in table:
                    t, notes = table[(s, a)]
                    db.execute("INSERT INTO translations VALUES (?,?,?,?,?)", (s, a, lang, t, notes))
                    tr[lang] = t
            records.append({
                "id": f"Q:{s}:{a}",
                "type": "quran",
                "text_ar": text,
                "translations": tr,
                "source": QURAN_SOURCE_AR,
                "ref": f"{name_ar}: {a}",
                "source_url": quran_url(s, a),
                "surah": s,
                "ayah": a,
                "topics": topics.get((s, a), []),
            })
            count += 1

    if count != EXPECTED_AYAHS:
        raise RuntimeError(f"expected {EXPECTED_AYAHS} ayahs, got {count}")
    for lang, table in translations.items():
        if len(table) != EXPECTED_AYAHS:
            raise RuntimeError(f"translation {lang} has {len(table)} ayahs")

    meta = {
        "quranpedia_version": manifest.get("version", ""),
        "mushaf": mushaf.get("name", ""),
        "mushaf_description": mushaf.get("description", ""),
        **{f"translation_{lang}": f"{config.QURAN_TRANSLATIONS[lang]}: {name}"
           for lang, name in book_names.items()},
    }
    db.executemany("INSERT INTO meta VALUES (?,?)", meta.items())
    db.commit()
    db.close()
    tmp_db.replace(config.VERBATIM_DB)

    out = config.PROCESSED_DIR / "quran.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Quran: {count} ayahs -> {config.VERBATIM_DB} and {out}")


if __name__ == "__main__":
    build()
