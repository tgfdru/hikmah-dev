"""POST /mueen/draft: the Sheykak app's format (paragraphs with their sources)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent import llm, settings
from api import mueen
from api.main import app
from retrieval import config as kb
from tests.agent_fakes import FakeLLM, analysis, draft, routing

KEY = {"X-API-Key": "k-test"}


def body(scope=None, messages=None):
    return {
        "questionId": "q_1",
        "question": {"title": "Why do Muslims worship the Kaaba?", "description": None},
        "messages": messages if messages is not None else [
            {"id": "m1", "text": "Why do Muslims worship the Kaaba?", "fromAsker": True},
            {"id": "m2", "text": "Welcome, let me explain.", "fromAsker": False},
            {"id": "m3", "text": "Isn't that idol worship?", "fromAsker": True},
        ],
        "scope": scope or {"kind": "all"},
    }


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(kb, "RETRIEVER", "mock")
    monkeypatch.setattr(settings, "RUN_LOG", tmp_path / "runs.jsonl")
    monkeypatch.setattr(settings, "API_KEYS", {"k-test"})
    monkeypatch.setattr(settings, "SERVICE_UNTIL", None)
    monkeypatch.setattr(settings, "VERIFY_LLM_JUDGE", False)
    with TestClient(app) as c:
        yield c
    llm.set_llm_factory(None)


def _script(level="A", reply=None, **kw):
    d = draft() if reply is None else draft(reply=reply, reply_ar=reply)
    return FakeLLM({"analyze": analysis(**kw), "route": routing(level), "generate": d})


def test_needs_the_api_key(client):
    assert client.post("/mueen/draft", json=body()).status_code == 401


def test_draft_in_the_app_shape(client):
    llm.set_llm_factory(_script())
    r = client.post("/mueen/draft", json=body(), headers=KEY)
    assert r.status_code == 200
    j = r.json()
    for key in ("id", "questionId", "scope", "paragraphs", "textMessageCount", "status", "notice"):
        assert key in j
    assert j["questionId"] == "q_1" and j["textMessageCount"] == 2 and j["status"] == "ok"
    p = j["paragraphs"][0]
    assert p["id"] == "p1" and "[[" not in p["text"]
    quran = [s for s in p["sources"] if s["kind"] == "quran"]
    assert quran and quran[0]["quote"].startswith("﴿") and quran[0]["quote"].endswith("﴾")
    # the exact text comes from the store, never from the model
    from agent.nodes import _verbatim
    assert quran[0]["quote"] == f"﴿{_verbatim('Q:2:144', 'en').text_ar}﴾"
    assert any(s["id"] == "QA:bayyinat:9" and s["kind"] == "other" for s in p["sources"])


def test_sources_follow_their_paragraph(client):
    reply = "Muslims worship Allah alone.\n\nThey face the Kaaba in prayer because Allah commanded it: [[Q:2:144]]"
    llm.set_llm_factory(_script(reply=reply))
    j = client.post("/mueen/draft", json=body(), headers=KEY).json()
    assert len(j["paragraphs"]) == 2
    assert not any(s["kind"] == "quran" for s in j["paragraphs"][0]["sources"])
    assert any(s["id"] == "Q:2:144" for s in j["paragraphs"][1]["sources"])


def test_personal_case_is_drafted_for_a_scholar_with_a_note(client):
    fake = _script(level="D", personal_case=True)
    llm.set_llm_factory(fake)
    j = client.post("/mueen/draft", json=body(), headers=KEY).json()
    assert j["status"] == "ok" and j["level"] == "D"
    assert "generate" in fake.stages() and "مستوى D" in j["notice"]
    assert j["paragraphs"]


def test_personal_case_still_refers_on_the_seeker_endpoint(client):
    fake = _script(level="D", personal_case=True)
    llm.set_llm_factory(fake)
    r = client.post("/suggest", json={"conversation_id": "c", "messages": [{"role": "seeker", "text": "x"}]},
                    headers=KEY)
    assert r.json()["status"] == "refer" and "generate" not in fake.stages()


def test_no_draft_gives_empty_paragraphs_and_a_notice(client, monkeypatch):
    monkeypatch.setattr(settings, "ABSTAIN_THRESHOLD", 1.01)  # nothing passes: abstain
    llm.set_llm_factory(_script())
    j = client.post("/mueen/draft", json=body(), headers=KEY).json()
    assert j["status"] == "abstain" and j["paragraphs"] == [] and j["notice"].startswith("لم يُعدّ معين")


def test_selected_scope_answers_the_picked_messages():
    req = mueen.MueenDraftRequest.model_validate(body(scope={"kind": "selected", "messageIds": ["m1"]}))
    msgs, count = mueen.to_conversation(req)
    assert count == 1
    assert msgs[-1] == {"role": "seeker", "text": "Why do Muslims worship the Kaaba?"}
    assert {"role": "dai", "text": "Welcome, let me explain."} in msgs


def test_whole_conversation_answers_what_came_after_the_scholars_reply():
    req = mueen.MueenDraftRequest.model_validate(body())
    msgs, count = mueen.to_conversation(req)
    assert count == 2 and msgs[-1] == {"role": "seeker", "text": "Isn't that idol worship?"}
    assert msgs[0]["text"].startswith("Why do Muslims")  # the question card comes first


def test_before_any_reply_the_card_and_follow_ups_are_answered_together():
    req = mueen.MueenDraftRequest.model_validate(body(messages=[
        {"id": "m1", "text": "And was he crucified?", "fromAsker": True}]))
    msgs, _ = mueen.to_conversation(req)
    assert len(msgs) == 1 and msgs[0]["role"] == "seeker"
    assert msgs[0]["text"].startswith("Why do Muslims worship the Kaaba?") and "crucified" in msgs[0]["text"]


def test_no_asker_text_is_rejected(client):
    llm.set_llm_factory(_script())
    b = body(messages=[{"id": "m2", "text": "Hello", "fromAsker": False}])
    b["question"] = None
    assert client.post("/mueen/draft", json=b, headers=KEY).status_code == 422


def test_run_log_keeps_no_text(client):
    llm.set_llm_factory(_script())
    client.post("/mueen/draft", json=body(), headers=KEY)
    logged = settings.RUN_LOG.read_text(encoding="utf-8")
    assert "Kaaba" not in logged and "idol" not in logged and "mueen_draft" in logged


@pytest.mark.parametrize("text,grade", [("صحيح", "sahih"), ("متفق عليه — صحيح", "sahih"), ("حسن", "hasan"),
                                        ("ضعيف", "daif"), ("Authentic", "sahih"), (None, None)])
def test_grade_mapping(text, grade):
    assert mueen._grade(text) == grade
