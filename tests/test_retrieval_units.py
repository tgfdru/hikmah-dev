from eval.run_eval import _matches
from retrieval.hybrid import point_id, rrf


def test_rrf_rewards_agreement():
    fused = dict(rrf([["a", "b", "c"], ["b", "a"], ["b"]]))
    assert max(fused, key=fused.get) == "b"
    assert fused["c"] < fused["a"]


def test_point_ids_are_stable_and_distinct():
    assert point_id("Q:2:255") == point_id("Q:2:255")
    assert point_id("Q:2:255") != point_id("QA:bayyinat:1")


def test_eval_id_matching():
    assert _matches("QA:bayyinat:9:3", "QA:bayyinat:9")
    assert not _matches("QA:bayyinat:90", "QA:bayyinat:9")
    assert _matches("Q:112:1-4", "Q:112:2") and _matches("Q:112:2", "Q:112:1-4")
    assert not _matches("Q:112:1", "Q:113:1")


def test_mock_retriever_contract():
    from retrieval.contract import Evidence
    from retrieval.mock import MockRetriever

    m = MockRetriever()
    ev = m.retrieve(["anything"], "en")
    assert len(ev) == 3 and all(isinstance(e, Evidence) for e in ev)
    assert m.get_verbatim(ev[0].id, "en").id == ev[0].id
    assert m.get_verbatim("Q:9:999", "en") is None
    assert [e.type for e in m.retrieve(["x"], "en", types=["qa"])] == ["qa"]


def test_arabic_queries_by_script():
    from retrieval.hybrid import _arabic_queries

    got = _arabic_queries(["What is Ramadan?", "ما هو رمضان", "رمضان کیا ہے", "Apa itu tauhid?"])
    assert got == {"ما هو رمضان"}  # fastText calls this short query Persian; Urdu stays out
