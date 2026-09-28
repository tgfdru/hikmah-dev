"""Parser tests on an HTML fragment shaped like Dorar's API answer.

The live API could not be reached from the dev machine (Cloudflare), so this
fixture reflects the documented format; re-check against a real response.
"""
from retrieval import dorar

FIXTURE = """
<div class="hadith" style="text-align:justify;">1 - إنَّما الأعمالُ <span class="search-keys">بالنِّيَّاتِ</span>، وإنَّما لِكُلِّ امرئٍ ما نَوى</div>
<div class="hadith-info"><span class="info-subtitle">الراوي:</span> عمر بن الخطاب <span class="info-subtitle">المحدث:</span> البخاري - <span class="info-subtitle">المصدر:</span> صحيح البخاري - <span class="info-subtitle">الصفحة أو الرقم:</span> 1 <br> <span class="info-subtitle">خلاصة حكم المحدث:</span> <span>[صحيح]</span></div>
<div class="hadith" style="text-align:justify;">2 - حديث آخر للاختبار فقط</div>
<div class="hadith-info"><span class="info-subtitle">الراوي:</span> فلان <span class="info-subtitle">المحدث:</span> الألباني - <span class="info-subtitle">المصدر:</span> ضعيف الجامع - <span class="info-subtitle">الصفحة أو الرقم:</span> 99 <br> <span class="info-subtitle">خلاصة حكم المحدث:</span> <span>ضعيف</span></div>
"""


def test_parse_results_fields():
    items = dorar.parse_results(FIXTURE)
    assert len(items) == 2
    h = items[0]
    assert h["text_ar"] == "إنَّما الأعمالُ بالنِّيَّاتِ ، وإنَّما لِكُلِّ امرئٍ ما نَوى"
    assert h["source"] == "صحيح البخاري" and h["number"] == "1" and "صحيح" in h["grade"]
    assert h["narrator"] == "عمر بن الخطاب"


def test_only_authentic_hadith_kept_and_ids():
    items = dorar.parse_results(FIXTURE)
    assert dorar.is_authentic(items[0]) and not dorar.is_authentic(items[1])
    assert dorar.hadith_id(items[0]) == "H:bukhari:1"
    assert dorar.hadith_id({"text_ar": "نص", "source": "سنن أبي داود", "number": "5"}).startswith("H:dorar:")


def test_fetch_failure_returns_empty(monkeypatch):
    import httpx

    def boom(*a, **k):
        raise httpx.ConnectError("blocked")

    monkeypatch.setattr(dorar.httpx, "get", boom)
    assert dorar.fetch("إنما الأعمال بالنيات") == []
