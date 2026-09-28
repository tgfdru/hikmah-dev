"""Mock retriever (RETRIEVER=mock): three fixed evidence items, no models, no index.

Lets the agent and API be developed and unit-tested without building the index.
Its items are real (copied from the verbatim store / Bayyinat), and its
get_verbatim resolves the same ids, so a verifier behaves like in production.
"""
from __future__ import annotations

from retrieval.contract import Evidence, SourceType

_ITEMS = [
    Evidence(
        id="Q:2:144", type="quran",
        text_ar=("قَدْ نَرَىٰ تَقَلُّبَ وَجْهِكَ فِي السَّمَاءِ ۖ فَلَنُوَلِّيَنَّكَ قِبْلَةً تَرْضَاهَا ۚ فَوَلِّ وَجْهَكَ "
                 "شَطْرَ الْمَسْجِدِ الْحَرَامِ ۚ وَحَيْثُ مَا كُنْتُمْ فَوَلُّوا وُجُوهَكُمْ شَطْرَهُ ۗ وَإِنَّ الَّذِينَ "
                 "أُوتُوا الْكِتَابَ لَيَعْلَمُونَ أَنَّهُ الْحَقُّ مِنْ رَبِّهِمْ ۗ وَمَا اللَّهُ بِغَافِلٍ عَمَّا يَعْمَلُونَ"),
        translation=None, source="القرآن الكريم", ref="البقرة: 144", grade=None,
        source_url="https://quranpedia.net/surah/1/2/144", score=0.82,
    ),
    Evidence(
        id="Q:112:1-4", type="quran",
        text_ar=("قُلْ هُوَ اللَّهُ أَحَدٌ ۝١ اللَّهُ الصَّمَدُ ۝٢ لَمْ يَلِدْ وَلَمْ يُولَدْ ۝٣ "
                 "وَلَمْ يَكُنْ لَهُ كُفُوًا أَحَدٌ ۝٤"),
        translation=None, source="القرآن الكريم", ref="الإخلاص: 1-4", grade=None,
        source_url="https://quranpedia.net/surah/1/112/1", score=0.71,
    ),
    Evidence(
        id="QA:bayyinat:9", type="qa",
        text_ar=("السؤال: لماذا يعبُدُ المسلِمون الكعبةَ، والحجَرَ الأسوَدَ؟\n"
                 "مختصر الإجابة: استقبالُ المسلِمين للكعبةِ في الصلاةِ ليس عبادةً لها؛ إذ المسلِمون لا يعبُدون "
                 "إلا اللهَ وحدَه ... وإنما جعَلَ اللهُ تعالى الكعبةَ الوِجْهةَ التي يتَّجِهُ المسلِمون إليها في "
                 "صلاتِهم؛ تقريرًا لعقيدةِ التوحيد."),
        translation=None, source="بينات: أسئلة وأجوبة عن الإسلام (مركز أصول)", ref="بينات، السؤال 9",
        grade=None,
        source_url="https://dawa.center/storage/files/AMYj6DfmHlSnZ766Zz0VlBNwmYtdwhAl31XMETlT.pdf#page=65",
        score=0.77,
    ),
]


def _resolve(e: Evidence, lang: str) -> Evidence:
    """Use the real verbatim store when it is built (exact translation); else Arabic only."""
    if e.type == "quran":
        try:
            from retrieval.verbatim import get_verbatim

            real = get_verbatim(e.id, lang)
            if real:
                return real.model_copy(update={"score": e.score})
        except FileNotFoundError:
            pass
    return e


class MockRetriever:
    def retrieve(self, queries: list[str], lang: str, types: list[SourceType] | None = None,
                 k: int = 6) -> list[Evidence]:
        return [_resolve(e, lang) for e in _ITEMS if not types or e.type in types][:k]

    def get_verbatim(self, ref_id: str, lang: str) -> Evidence | None:
        for e in _ITEMS:
            if e.id == ref_id:
                return _resolve(e, lang).model_copy(update={"score": 1.0})
        return None
