from ingest.pdf_ar import _fix_ligatures, fix_text


def _u(chars):
    """Units as the extractor builds them: (char, x origin, width)."""
    return [{"base": c, "text": c, "x": x, "w": w} for c, x, w in chars]


def _s(units):
    return "".join(u["text"] for u in units)


def test_lam_alef_components_are_reordered():
    # "الإسلام" extracted as ا(88.6) إ(88.6) ل س(73.1) ا(73.1) ل م
    units = _u([("ا", 88.6, 2.8), ("إ", 88.6, 0), ("ل", 80.5, 8), ("س", 73.1, 8), ("ا", 73.1, 0),
                ("ل", 64.5, 8), ("م", 58.6, 6)])
    assert _s(_fix_ligatures(units)) == "الإسلام"


def test_lillah_ligature():
    units = _u([("ا", 390.1, 2.7), ("ه", 390.1, 0), ("ل", 390.1, 0), ("ل", 381.0, 9.1)])
    assert _s(_fix_ligatures(units)) == "الله"


def test_fi_ligature_and_genuine_words_untouched():
    assert _s(_fix_ligatures(_u([(" ", 10, 2), ("ي", 10, 0), ("ف", 5, 8)]))) == " في"
    # "كيف": ي has width and its own origin -> unchanged
    assert _s(_fix_ligatures(_u([("ك", 370, 6), ("ي", 365, 4.7), ("ف", 351, 14)]))) == "كيف"
    # the article "ال": alef has width -> unchanged
    assert _s(_fix_ligatures(_u([("ا", 50, 2.8), ("ل", 45, 8), ("ك", 38, 6)]))) == "الك"


def test_text_level_fallbacks():
    assert fix_text("اإلسالم") == "الإسالم"  # first ligature fixable from text alone
    assert fix_text("وجودُ هللاِ") == "وجودُ اللهِ"
    assert fix_text("باهلل") == "بالله"
    assert fix_text("ال بدَّ له") == "لا بدَّ له"
    assert fix_text("يف منصة") == "في منصة"
    assert fix_text("لَ تَضُرُّ وَلَ تَنْفَعُ") == "لَا تَضُرُّ وَلَا تَنْفَعُ"
    assert fix_text("فضلً إذا") == "فضلًا إذا"


def test_text_fallbacks_do_not_touch_correct_arabic():
    for good in ["قَالَ لَهُ", "جَعَلَ اللهُ", "حالَ دون", "كيف حالك", "لماذا لا", "فَالَ", "هلال"]:
        assert fix_text(good) == good
