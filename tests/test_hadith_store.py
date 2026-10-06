"""HadeethEnc lookups through get_verbatim (a tiny synthetic store: placeholder text, not hadith)."""
from __future__ import annotations

import json
import sqlite3

import pytest

from retrieval import config, verbatim


@pytest.fixture
def store(tmp_path, monkeypatch):
    db = tmp_path / "hadith.sqlite"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE hadith (id TEXT PRIMARY KEY, title_ar TEXT, text_ar TEXT NOT NULL, attribution_ar TEXT, "
              "grade_ar TEXT NOT NULL, explanation_ar TEXT, reference_ar TEXT, translations TEXT NOT NULL, url TEXT NOT NULL)")
    c.execute("INSERT INTO hadith VALUES (?,?,?,?,?,?,?,?,?)", (
        "7", "عنوان", "نص اختباري", "متفق عليه", "صحيح", "", "",
        json.dumps({"en": {"hadeeth": "placeholder text", "grade": "Authentic"}}),
        "https://hadeethenc.com/ar/browse/hadith/7"))
    c.commit()
    c.close()
    monkeypatch.setattr(config, "HADITH_DB", db)
    monkeypatch.setattr(verbatim, "_hadith_local", type(verbatim._hadith_local)())
    return db


def test_known_id_returns_exact_text_grade_and_translation(store):
    e = verbatim.get_hadith("H:hadeethenc:7", "en")
    assert e.type == "hadith" and e.text_ar == "نص اختباري" and e.grade == "صحيح" and e.ref == "متفق عليه"
    assert e.translation == "placeholder text" and e.source_url.endswith("/en/browse/hadith/7")


def test_arabic_and_untranslated_languages_have_no_translation(store):
    assert verbatim.get_hadith("H:hadeethenc:7", "ar").translation is None
    e = verbatim.get_hadith("H:hadeethenc:7", "ur")
    assert e.translation is None and "/ar/" in e.source_url


@pytest.mark.parametrize("rid", ["H:hadeethenc:999", "H:hadeethenc:abc", "H:hadeethenc:", "H:hadeethenc:7; drop"])
def test_unknown_or_malformed_ids_are_none(store, rid):
    assert verbatim.get_hadith(rid, "en") is None


def test_missing_store_means_no_hadith(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HADITH_DB", tmp_path / "absent.sqlite")
    monkeypatch.setattr(verbatim, "_hadith_local", type(verbatim._hadith_local)())
    assert verbatim.get_hadith("H:hadeethenc:7", "en") is None
