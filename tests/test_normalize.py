from retrieval.normalize_ar import has_arabic, norm, strip_diacritics, tokenize


def test_norm_removes_diacritics_and_unifies_letters():
    assert norm("قُلْ هُوَ اللَّهُ أَحَدٌ") == "قل هو الله احد"
    assert norm("إِنَّ الدِّينَ عِندَ اللَّهِ الْإِسْلَامُ") == "ان الدين عند الله الاسلام"
    assert norm("مَدْرَسَة") == "مدرسه"
    assert norm("عَلَى") == "علي"
    assert norm("ٱلرَّحْمَٰنِ") == "الرحمن"  # alef wasla + dagger alef


def test_norm_strips_invisible_characters_and_tatweel():
    assert norm("﻿الـــله") == "الله"


def test_strip_diacritics_keeps_letters():
    assert strip_diacritics("أَحَدٌ") == "أحد"


def test_tokenize_arabic_and_english():
    toks = tokenize("Why do Muslims face the Kaaba? لماذا يستقبل المسلمون الكعبة")
    assert "kaaba" in toks and "muslims" in toks
    assert "كعبه" in toks  # "ال" stripped, ة -> ه
    assert "why" not in toks and "لماذا" not in toks  # stop words


def test_has_arabic():
    assert has_arabic("what is توحيد")
    assert not has_arabic("hello")
