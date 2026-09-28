from ingest.quran import clean_translation


def test_clean_translation_splits_footnotes_and_markers():
    raw = ('1.\xa0Say (O Muhammad): "He is Allâh, (the) One.[1]<br />\n____________________<br />\n'
           "(V.112:1) See Tauhîd in the Glossary (Appendix).")
    text, notes = clean_translation(raw)
    assert text == 'Say (O Muhammad): "He is Allâh, (the) One.'
    assert notes.startswith("(V.112:1)")


def test_clean_translation_urdu_stars_and_presentation_forms():
    text, notes = clean_translation("زنده اور سب کا تھامنے واﻻ ہے*، اس کی<br />\n____________________<br />\n* نوٹ")
    assert "*" not in text and "ﻻ" not in text and "والا" in text
    assert notes == "* نوٹ"
