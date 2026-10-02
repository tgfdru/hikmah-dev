"""HTTP API: shape, access control, service end date, feedback and stats."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from agent import llm, settings
from api.main import app
from retrieval import config as kb
from tests.agent_fakes import FakeLLM, analysis, draft, routing

BODY = {"conversation_id": "c_1", "messages": [{"role": "seeker", "text": "Why do Muslims worship the Kaaba?"}]}


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(kb, "RETRIEVER", "mock")
    monkeypatch.setattr(settings, "RUN_LOG", tmp_path / "runs.jsonl")
    monkeypatch.setattr(settings, "API_KEYS", {"k-test"})
    monkeypatch.setattr(settings, "SERVICE_UNTIL", None)
    monkeypatch.setattr(settings, "VERIFY_LLM_JUDGE", False)
    llm.set_llm_factory(FakeLLM({"analyze": analysis(), "route": routing("A"), "generate": draft()}))
    with TestClient(app) as c:
        yield c
    llm.set_llm_factory(None)


def test_health_needs_no_key(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["auth_required"] is True


def test_missing_or_wrong_key_is_401(client):
    assert client.post("/suggest", json=BODY).status_code == 401
    assert client.post("/suggest", json=BODY, headers={"X-API-Key": "nope"}).status_code == 401


def test_suggest_shape_matches_eval_contract(client):
    r = client.post("/suggest", json=BODY, headers={"X-API-Key": "k-test"})
    assert r.status_code == 200
    j = r.json()
    for key in ("status", "level", "reply", "reply_ar", "citations", "latency_ms", "note_for_dai", "suggestion_id"):
        assert key in j
    assert j["status"] == "ok" and j["citations"][0]["id"]
    assert j["ai_generated"] is True


def test_service_end_date_blocks_requests(client, monkeypatch):
    monkeypatch.setattr(settings, "SERVICE_UNTIL", date.today() - timedelta(days=1))
    r = client.post("/suggest", json=BODY, headers={"X-API-Key": "k-test"})
    assert r.status_code == 403 and "ended" in r.json()["detail"]


def test_run_log_has_no_message_text_and_stats_work(client):
    r = client.post("/suggest", json=BODY, headers={"X-API-Key": "k-test"})
    sid = r.json()["suggestion_id"]
    client.post("/feedback", headers={"X-API-Key": "k-test"},
                json={"conversation_id": "c_1", "suggestion_id": sid, "action": "sent_as_is"})
    logged = settings.RUN_LOG.read_text(encoding="utf-8")
    assert "Kaaba" not in logged and "worship" not in logged
    s = client.get("/stats", headers={"X-API-Key": "k-test"}).json()
    assert s["suggest"] == 1 and s["accepted_as_is_rate"] == 1.0


def test_regenerate_requires_valid_style(client):
    bad = client.post("/suggest/regenerate", json={**BODY, "style": "funny"}, headers={"X-API-Key": "k-test"})
    assert bad.status_code == 422
    ok = client.post("/suggest/regenerate", json={**BODY, "style": "shorter"}, headers={"X-API-Key": "k-test"})
    assert ok.status_code == 200


def test_llm_not_configured_is_503(client, monkeypatch):
    llm.set_llm_factory(None)
    monkeypatch.setattr(settings, "AI_API_KEY", "")
    monkeypatch.setattr(settings, "MODEL_ANALYZE", "paid-model")  # *-free models need no key
    r = client.post("/suggest", json=BODY, headers={"X-API-Key": "k-test"})
    assert r.status_code == 503
