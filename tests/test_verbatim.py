from retrieval.quran_meta import parse_quran_ref
from tests.conftest import needs_store


def test_parse_quran_ref():
    assert parse_quran_ref("Q:2:255").id == "Q:2:255"
    assert parse_quran_ref("Q:112:1-4").id == "Q:112:1-4"
    for bad in ["Q:0:1", "Q:115:1", "Q:2:5-3", "H:bukhari:1", "Q:2", "2:255"]:
        assert parse_quran_ref(bad) is None


@needs_store
def test_single_ayah_with_translations():
    from retrieval.verbatim import get_verbatim

    from retrieval.normalize_ar import norm

    e = get_verbatim("Q:112:1", "en")
    assert norm(e.text_ar) == "قل هو الله احد" and e.text_ar.startswith("قُلْ")
    assert e.ref == "الإخلاص: 1" and e.source == "القرآن الكريم" and e.score == 1.0
    assert "Allâh" in e.translation
    assert get_verbatim("Q:112:1", "ar").translation is None
    assert "اللہ" in get_verbatim("Q:112:1", "ur").translation


@needs_store
def test_range_merges_ayahs_with_markers():
    from retrieval.verbatim import get_verbatim

    e = get_verbatim("Q:112:1-4", "en")
    assert e.text_ar.count("۝") == 4 and e.ref == "الإخلاص: 1-4"
    assert e.translation.startswith("(1)") and "(4)" in e.translation


@needs_store
def test_unknown_references_return_none():
    from retrieval.verbatim import get_verbatim

    for ref in ["Q:2:287", "Q:1:8", "Q:999:1", "Q:2:1-300", "H:bukhari:999999", "QA:bayyinat:1", ""]:
        assert get_verbatim(ref, "en") is None


@needs_store
def test_every_ayah_present_and_translations_complete():
    from retrieval.verbatim import get_store

    db = get_store().db
    assert db.execute("SELECT COUNT(*) FROM ayahs").fetchone()[0] == 6236
    for lang in ("en", "ur"):
        assert db.execute("SELECT COUNT(*) FROM translations WHERE lang=?", (lang,)).fetchone()[0] == 6236
    # no leftover HTML or footnote markers in translations
    assert db.execute("SELECT COUNT(*) FROM translations WHERE text LIKE '%<br%' OR text LIKE '%[1]%'")\
        .fetchone()[0] == 0


@needs_store
def test_other_languages_fall_back_to_english():
    from retrieval.verbatim import get_verbatim

    assert get_verbatim("Q:1:1", "tl").translation == get_verbatim("Q:1:1", "en").translation


@needs_store
def test_quran_refs_in_text():
    from retrieval.verbatim import quran_refs_in

    text = "قال تعالى ﴿...﴾ [البقرة: 144] وقال ﴿...﴾ [آل عمران: 96-97] و[النور: 999]"
    assert quran_refs_in(text) == ["Q:2:144", "Q:3:96-97"]


@needs_store
def test_quran_refs_in_shamela_formats():
    from retrieval.verbatim import quran_refs_in

    text = "قال تعالى ﴿...﴾ [المائدة:٥٠] وقال ﴿...﴾ (الحديد: ٢٧) و(سورة الإخلاص: ١-٤)"
    assert quran_refs_in(text) == ["Q:5:50", "Q:57:27", "Q:112:1-4"]
