import pytest

from retrieval.langid import MODEL_PATH, detect_language

pytestmark = pytest.mark.skipif(not MODEL_PATH.exists(), reason="run: python -m ingest.download")


def test_basic_languages():
    assert detect_language("لماذا يعبد المسلمون الكعبة؟")[0] == "ar"
    assert detect_language("مسلمان کعبہ کی عبادت کیوں کرتے ہیں؟")[0] == "ur"
    assert detect_language("Is Islam true?")[0] == "en"  # fastText alone says Malay


def test_a_few_english_words_do_not_flip_an_urdu_reply():
    reply = ("پہلے اس بات کو صاف کر لیں: مسلمان **The Ka'bah** (کعبہ) کو ایک پتھر یا عمارت کو نہیں "
             "عبادت کرتے، بلکہ صرف اللہ تعالیٰ کو۔ اللہ نے خود اسے قبلہ (وہ direction جس کی طرف نماز میں "
             "منہ کرنا لازم ہے) مقرر کیا ہے۔")
    assert detect_language(reply)[0] == "ur"


def test_quoted_arabic_does_not_change_the_language():
    assert detect_language("The Quran says «قل هو الله واحد» right? What does it mean?")[0] == "en"
    assert detect_language("قرآن میں ہے ﴿لَا إِكْرَاهَ فِي الدِّينِ﴾ [البقرة: 256]، اس کا کیا مطلب ہے؟")[0] == "ur"
