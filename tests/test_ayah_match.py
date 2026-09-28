from tests.conftest import needs_store


@needs_store
def test_detects_misquote_and_exact_quote():
    from retrieval.ayah_match import match_ayah

    m = match_ayah("قل هو الله واحد")
    assert m.ref_id == "Q:112:1" and not m.is_exact and 0.85 < m.similarity < 1
    m = match_ayah("قُلْ هُوَ اللَّهُ أَحَدٌ")
    assert m.ref_id == "Q:112:1" and m.is_exact


@needs_store
def test_quote_across_two_ayahs():
    from retrieval.ayah_match import match_ayah

    m = match_ayah("الحمد لله رب العالمين الرحمن الرحيم")
    assert m.ref_id == "Q:1:2-3" and m.is_exact


@needs_store
def test_non_quran_text_is_not_matched():
    from retrieval.ayah_match import match_ayah

    assert match_ayah("هذه جملة عادية ليست من القرآن الكريم") is None
    assert match_ayah("short") is None


@needs_store
def test_find_quotes_in_message():
    from retrieval.ayah_match import find_quran_quotes

    found = find_quran_quotes('He said the Quran says «قل هو الله واحد» and "إن الدين عند الله الإسلام".')
    assert [m.ref_id for m in found] == ["Q:112:1", "Q:3:19"]
    assert [m.is_exact for m in found] == [False, True]
