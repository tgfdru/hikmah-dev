"""End-to-end retrieval on the built index (skipped until `python -m ingest.build_all`)."""
import pytest

from tests.conftest import needs_index

pytestmark = needs_index


@pytest.fixture(scope="module")
def retriever():
    from retrieval.hybrid import get_hybrid

    r = get_hybrid()
    r.reranker = "none"
    return r


def test_kaaba_question_finds_bayyinat_answer(retriever):
    ev = retriever.retrieve(["Why do Muslims worship the Kaaba?", "لماذا يعبد المسلمون الكعبة"], "en")
    assert len(ev) == 6
    assert any(e.id.startswith("QA:bayyinat:9") for e in ev[:2])
    assert all(0 <= e.score <= 1 for e in ev)
    assert [e.score for e in ev] == sorted((e.score for e in ev), reverse=True)


def test_quran_evidence_uses_verbatim_text_and_language(retriever):
    from retrieval.verbatim import get_verbatim

    ev = retriever.retrieve(["مسلمان کعبہ کی عبادت کیوں کرتے ہیں؟"], "ur", types=["quran"])
    assert ev and all(e.type == "quran" for e in ev)
    for e in ev:
        exact = get_verbatim(e.id, "ur")
        assert e.text_ar == exact.text_ar and e.translation == exact.translation


def test_at_most_two_parts_per_bayyinat_question(retriever):
    ev = retriever.retrieve(["Was Islam spread by the sword?", "هل انتشر الإسلام بالسيف"], "en", types=["qa"])
    parents = [e.id.split(":")[2] for e in ev]
    assert max(parents.count(p) for p in parents) <= 2


def test_unrelated_question_scores_below_threshold(retriever):
    from retrieval import config

    ev = retriever.retrieve(["What is the capital of France?"], "en")
    assert ev[0].score < config.ABSTAIN_THRESHOLDS["none"]


def test_fake_hadith_request_finds_nothing_above_the_threshold(retriever):
    """No hadith in the store is about computers: abstain (empty without HadeethEnc)."""
    from retrieval import config

    ev = retriever.retrieve(["حديث عن الحاسوب"], "ar", types=["hadith"])
    assert all(e.type == "hadith" for e in ev)
    assert not ev or ev[0].score < config.ABSTAIN_THRESHOLDS["none"]


def test_hadith_evidence_comes_from_the_store_with_grade(retriever):
    from retrieval.verbatim import get_verbatim

    ev = retriever.retrieve(["Is there a hadith about intentions?", "حديث عن النية في الأعمال"], "en",
                            types=["hadith"])
    if not ev:
        pytest.skip("index built without HadeethEnc (python -m ingest.build_all --hadith)")
    for e in ev:
        exact = get_verbatim(e.id, "en")
        assert e.id.startswith("H:hadeethenc:") and e.text_ar == exact.text_ar and e.grade


def _has_shamela(r) -> bool:
    return r.manifest.get("counts", {}).get("dawah", 0) > 0


def test_shamela_passages_cite_book_page_and_link(retriever):
    if not _has_shamela(retriever):
        pytest.skip("index built without Shamela (python -m ingest.build_all --shamela)")
    ev = retriever.retrieve(["Is Jesus the son of God?", "هل المسيح ابن الله"], "en", types=["dawah"])
    assert ev and all(e.id.startswith("SH:") and e.type == "dawah" for e in ev)
    for e in ev:
        book = e.id.split(":")[1]
        assert e.source_url.startswith(f"https://shamela.ws/book/{book}/")
        assert e.ref and e.translation is None


def test_at_most_two_passages_per_shamela_book(retriever):
    if not _has_shamela(retriever):
        pytest.skip("index built without Shamela")
    ev = retriever.retrieve(["Is Jesus the son of God?", "هل المسيح ابن الله"], "en", types=["dawah"], k=8)
    books = [e.id.split(":")[1] for e in ev]
    assert max(books.count(b) for b in books) <= 2
