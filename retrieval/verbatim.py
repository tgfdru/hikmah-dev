"""Verbatim store: the only source of Quran text shown to users.

`get_verbatim("Q:2:255", "en")` returns the exact Arabic text of the ayah plus the
approved translation for that language. Ranges ("Q:112:1-4") are merged with
ayah-number markers. Unknown or malformed ids return None, which is how the
agent's verifier detects a hallucinated reference.

Hadith: `H:hadeethenc:<id>` comes from the HadeethEnc store (store/hadith.sqlite, built
by ingest/hadeethenc.py): exact Arabic text, grade, attribution and approved translations.
Other `H:` ids are hadith cached from the optional Dorar tool (retrieval/dorar.py). Both go
through the same `get_verbatim` call, so the verifier treats them like the Quran.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
from functools import lru_cache
from pathlib import Path

from retrieval import config
from retrieval.contract import Evidence
from retrieval.quran_meta import QURAN_SOURCE_AR, parse_quran_ref, quran_url

_ARABIC_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
MAX_RANGE = 40  # longest range we will render in one Evidence


def ayah_marker(n: int) -> str:
    """The end-of-ayah ornament with Arabic-Indic digits, e.g. ﴿...﴾ ٢٥٥."""
    return f"۝{str(n).translate(_ARABIC_DIGITS)}"


class VerbatimStore:
    def __init__(self, path: Path | None = None):
        self.path = Path(path or config.VERBATIM_DB)
        if not self.path.exists():
            raise FileNotFoundError(
                f"{self.path} not found. Build it with: python -m ingest.build_all --only quran"
            )
        self._local = threading.local()

    @property
    def db(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, check_same_thread=False)
            self._local.conn = conn
        return conn

    def surah_name(self, surah: int, lang: str = "ar") -> str | None:
        row = self.db.execute("SELECT name_ar, name_en FROM surahs WHERE surah=?", (surah,)).fetchone()
        if not row:
            return None
        return row[0] if lang == "ar" else row[1]

    def ayah_count(self, surah: int) -> int:
        row = self.db.execute("SELECT ayah_count FROM surahs WHERE surah=?", (surah,)).fetchone()
        return row[0] if row else 0

    def meta(self) -> dict[str, str]:
        return dict(self.db.execute("SELECT key, value FROM meta").fetchall())

    def iter_ayahs(self):
        """Yield (surah, ayah, text_ar, text_norm) for every ayah (used by match_ayah)."""
        yield from self.db.execute(
            "SELECT surah, ayah, text_ar, text_norm FROM ayahs ORDER BY surah, ayah"
        )

    def translation_lang(self, lang: str) -> str | None:
        """Which stored translation serves `lang` (None for Arabic)."""
        lang = (lang or "").lower().split("-")[0]
        if lang == "ar":
            return None
        if lang in config.QURAN_TRANSLATIONS:
            return lang
        return "en"  # fallback for languages without an approved translation yet

    def get_quran(self, ref_id: str, lang: str) -> Evidence | None:
        ref = parse_quran_ref(ref_id)
        if ref is None or ref.end - ref.start + 1 > MAX_RANGE:
            return None
        if ref.end > self.ayah_count(ref.surah):
            return None
        rows = self.db.execute(
            "SELECT ayah, text_ar FROM ayahs WHERE surah=? AND ayah BETWEEN ? AND ? ORDER BY ayah",
            (ref.surah, ref.start, ref.end),
        ).fetchall()
        if len(rows) != ref.end - ref.start + 1:
            return None
        tr_lang = self.translation_lang(lang)
        translation = None
        if tr_lang:
            trs = self.db.execute(
                "SELECT ayah, text FROM translations WHERE surah=? AND lang=? AND ayah BETWEEN ? AND ?"
                " ORDER BY ayah",
                (ref.surah, tr_lang, ref.start, ref.end),
            ).fetchall()
            if len(trs) == len(rows):
                translation = (
                    trs[0][1] if len(trs) == 1 else " ".join(f"({a}) {t}" for a, t in trs)
                )
        if len(rows) == 1:
            text_ar = rows[0][1]
        else:
            text_ar = " ".join(f"{t} {ayah_marker(a)}" for a, t in rows)
        name = self.surah_name(ref.surah, "ar")
        verses = str(ref.start) if ref.start == ref.end else f"{ref.start}-{ref.end}"
        return Evidence(
            id=ref.id,
            type="quran",
            text_ar=text_ar,
            translation=translation,
            source=QURAN_SOURCE_AR,
            ref=f"{name}: {verses}",
            grade=None,
            source_url=quran_url(ref.surah, ref.start),
            score=1.0,
        )

    def get(self, ref_id: str, lang: str) -> Evidence | None:
        ref_id = (ref_id or "").strip()
        if ref_id.startswith("Q:"):
            return self.get_quran(ref_id, lang)
        if ref_id.startswith("H:hadeethenc:"):
            return get_hadith(ref_id, lang)
        if ref_id.startswith("H:"):
            from retrieval import dorar  # cached hadith from the optional Dorar tool

            return dorar.get_cached(ref_id, lang)
        return None


# "[البقرة: 144]", "[المائدة:٥٠]", "(الحديد: ٢٧)", "[آل عمران: 96-97]", optionally "سورة ...".
_REF_IN_TEXT = re.compile(
    r"[\[(](?:سورة\s+)?([\u0621-\u064a ]{2,20}?)\s*:\s*([\d\u0660-\u0669]{1,3})"
    r"(?:\s*[-–]\s*([\d\u0660-\u0669]{1,3}))?\s*[\])]"
)
_INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def quran_refs_in(text: str) -> list[str]:
    """Quran ids cited in a text as "[البقرة: 144]", "(المائدة: ٥٠)" or "[آل عمران: 96-97]".

    Bayyinat evidence quotes verses this way; the agent can allow these ids in
    its [[Q:...]] placeholders because the verses are part of that evidence.
    """
    store = get_store()
    names = _surah_numbers(store)
    out = []
    for name, a, b in _REF_IN_TEXT.findall(text or ""):
        s = names.get(name.strip())
        a, b = a.translate(_INDIC), b.translate(_INDIC)
        if s:
            ref = f"Q:{s}:{a}" if not b else f"Q:{s}:{a}-{b}"
            if store.get_quran(ref, "ar") and ref not in out:
                out.append(ref)
    return out


@lru_cache(maxsize=1)
def _surah_numbers(store: "VerbatimStore") -> dict[str, int]:
    return {store.surah_name(s, "ar"): s for s in range(1, 115)}


HADITH_SOURCE_AR = "موسوعة الأحاديث النبوية المترجمة (HadeethEnc)"
_hadith_local = threading.local()


def _hadith_db() -> sqlite3.Connection | None:
    conn = getattr(_hadith_local, "conn", None)
    if conn is None:
        if not config.HADITH_DB.exists():
            return None
        conn = sqlite3.connect(f"file:{config.HADITH_DB}?mode=ro", uri=True, check_same_thread=False)
        _hadith_local.conn = conn
    return conn


def get_hadith(ref_id: str, lang: str) -> Evidence | None:
    """A HadeethEnc hadith: exact Arabic text, its grade and attribution, and the approved
    translation for `lang` (None for Arabic or when HadeethEnc has none in that language)."""
    m = re.fullmatch(r"H:hadeethenc:(\d+)", (ref_id or "").strip())
    db = _hadith_db()
    if not m or db is None:
        return None
    row = db.execute("SELECT text_ar, attribution_ar, grade_ar, translations, url FROM hadith WHERE id = ?",
                     (m.group(1),)).fetchone()
    if not row:
        return None
    text_ar, attribution, grade, translations, url = row
    tr = json.loads(translations).get(lang) if lang != "ar" else None
    return Evidence(
        id=f"H:hadeethenc:{m.group(1)}", type="hadith", text_ar=text_ar,
        translation=(tr or {}).get("hadeeth"), source=HADITH_SOURCE_AR, ref=attribution or "",
        grade=grade, source_url=url.replace("/ar/", f"/{lang}/") if tr else url, score=1.0,
    )


@lru_cache(maxsize=1)
def get_store() -> VerbatimStore:
    return VerbatimStore()


def get_verbatim(ref_id: str, lang: str) -> Evidence | None:
    """Exact text for a Quran reference or a hadith (HadeethEnc / cached Dorar); None if unknown."""
    return get_store().get(ref_id, lang)
