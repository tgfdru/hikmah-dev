"""End-to-end agent graph with RETRIEVER=mock and a scripted LLM (offline)."""
from __future__ import annotations

import pytest

from agent import llm, settings, templates
from agent.graph import suggest
from retrieval import config as kb
from tests.agent_fakes import FakeLLM, analysis, draft, routing

KAABA = [{"role": "seeker", "text": "Why do Muslims worship the Kaaba?"}]


@pytest.fixture(autouse=True)
def mock_world(monkeypatch):
    monkeypatch.setattr(kb, "RETRIEVER", "mock")
    monkeypatch.setattr(settings, "VERIFY_LLM_JUDGE", False)
    monkeypatch.setattr(settings, "MAX_DRAFT_ATTEMPTS", 2)
    monkeypatch.setattr(settings, "ABSTAIN_THRESHOLD", 0.35)
    yield
    llm.set_llm_factory(None)


def run(script, messages=KAABA, **kw):
    fake = FakeLLM(script)
    llm.set_llm_factory(fake)
    return suggest(messages, **kw), fake


def test_happy_path_inserts_exact_verse_from_store():
    out, fake = run({"analyze": analysis(), "route": routing("A"), "generate": draft()})
    assert out["status"] == "ok" and out["level"] == "A"
    assert fake.stages() == ["analyze", "route", "generate"]
    assert "[[" not in out["reply"]
    # exact verse text comes from the store (here the mock), never from the model or this test
    from retrieval.mock import MockRetriever
    assert f"﴿{MockRetriever().get_verbatim('Q:2:144', 'en').text_ar}﴾" in out["reply"]
    assert {c["id"] for c in out["citations"]} == {"Q:2:144", "QA:bayyinat:9"}
    assert out["trace"] == ["analyze", "route", "retrieve", "generate", "verify"]


def test_fabricated_reference_is_retried_then_accepted():
    bad = draft(reply="See [[Q:2:300]]", reply_ar="انظر [[Q:2:300]]", cited_ids=["Q:2:300"])
    out, fake = run({"analyze": analysis(), "route": routing("A"), "generate": [bad, draft()]})
    assert out["status"] == "ok" and out["attempts"] == 2
    retry_prompt = fake.calls[-1][1][1][1]
    assert "Q:2:300" in retry_prompt and "rejected by the verifier" in retry_prompt


def test_second_failure_is_shown_as_unverified_not_hidden():
    bad = draft(reply="See [[Q:2:300]]", reply_ar="انظر [[Q:2:300]]", cited_ids=["Q:2:300"])
    out, _ = run({"analyze": analysis(), "route": routing("A"), "generate": bad})
    assert out["status"] == "unverified" and out["issues"]
    assert "unverified reference" in out["reply"] and "⚠" in out["note_for_dai"]


def test_model_writing_quran_brackets_is_rejected():
    sneaky = draft(reply="As Allah says ﴿some text﴾ [[Q:2:144]]")
    out, _ = run({"analyze": analysis(), "route": routing("A"), "generate": [sneaky, draft()]})
    assert out["attempts"] == 2 and out["status"] == "ok"


def test_level_c_consensus_claim_is_rejected():
    claim = draft(reply="All Muslims agree that this is forbidden. [[Q:2:144]]")
    out, _ = run({"analyze": analysis(), "route": routing("C"), "generate": [claim, draft()]})
    assert out["level"] == "C" and out["attempts"] == 2 and out["status"] == "ok"


def test_level_d_refers_without_retrieval_or_generation():
    msgs = [{"role": "seeker", "text": "I'm in France, can I marry only at the city hall?"}]
    out, fake = run({"analyze": analysis(personal_case=True), "route": routing("B")}, messages=msgs)
    # analyzer + keyword rule agree on a personal case -> raised to D even though the LLM said B
    assert out["status"] == "refer" and out["level"] == "D"
    assert out["reply"] == templates.REFER["en"] and out["citations"] == []
    assert "generate" not in fake.stages() and "retrieve" not in out["trace"]


def test_router_d_decision_is_respected():
    out, _ = run({"analyze": analysis(language="ar"), "route": routing("D", "حالة شخصية")},
                 messages=[{"role": "seeker", "text": "طلقت زوجتي وأنا غاضب فهل وقع الطلاق؟"}])
    assert out["status"] == "refer" and out["reply"] == templates.REFER["ar"]


def test_hadith_request_abstains_when_no_hadith_in_sources():
    msgs = [{"role": "seeker", "text": "أعطني حديثًا يثبت أن النبي كان يستخدم الحاسوب"}]
    out, fake = run({"analyze": analysis(language="ar", asks_for_hadith=True), "route": routing("B")},
                    messages=msgs)
    assert out["status"] == "abstain" and out["reply"] == templates.ABSTAIN_HADITH["ar"]
    assert "«" not in out["reply"] and not out["citations"]
    assert "generate" not in fake.stages()


def test_low_confidence_abstains(monkeypatch):
    monkeypatch.setattr(settings, "ABSTAIN_THRESHOLD", 0.95)
    out, _ = run({"analyze": analysis(), "route": routing("B")})
    assert out["status"] == "abstain" and out["reply"] == templates.ABSTAIN["en"]


def test_rare_language_template_is_translated_by_llm():
    out, fake = run({"analyze": analysis(language="tl", personal_case=True), "route": routing("D"),
                     "translate": type("M", (), {"content": "Salamat sa tanong mo..."})()},
                    messages=[{"role": "seeker", "text": "Pwede ba akong magpakasal sa city hall lang?"}])
    assert out["status"] == "refer" and out["reply"].startswith("Salamat")
    assert "translate" in fake.stages()


def test_regenerate_style_reaches_the_prompt():
    out, fake = run({"analyze": analysis(), "route": routing("A"), "generate": draft()}, style="simpler")
    gen_prompt = [m for s, m in fake.calls if s == "generate"][0][1][1]
    assert "simpler" in gen_prompt.lower()


def test_unknown_cited_id_is_an_issue():
    from agent.nodes import check_draft
    from retrieval.mock import MockRetriever

    ev = MockRetriever().retrieve(["x"], "en")
    issues = check_draft(draft(cited_ids=["QA:bayyinat:999"]), ev, "en", "A")
    assert any("QA:bayyinat:999" in i for i in issues)
    assert check_draft(draft(), ev, "en", "A") == []


def test_malformed_nested_tool_call_is_repaired():
    nested = {"raw_args": {"language": "en", "knowledge_level": "beginner", "background": "unknown",
                           "tone": "curious", "core_question": {
                               "core_question": "لماذا يعبد المسلمون الكعبة؟", "arabic_query": "الكعبة القبلة",
                               "asks_for_hadith": False, "personal_case": False}}}
    out, _ = run({"analyze": nested, "route": routing("A"), "generate": draft()})
    assert out["status"] == "ok"


def test_unrepairable_output_is_retried():
    broken = {"raw_args": {"language": "en"}}
    out, fake = run({"analyze": [broken, analysis()], "route": routing("A"), "generate": draft()})
    assert out["status"] == "ok" and fake.stages().count("analyze") == 2


def test_term_question_without_evidence_uses_glossary(monkeypatch):
    monkeypatch.setattr(settings, "ABSTAIN_THRESHOLD", 0.95)    # no search evidence passes
    msgs = [{"role": "seeker", "text": "What does Tawhid mean? I have never heard this word before."}]
    gdraft = draft(reply="Tawhid means believing that God is One ...", reply_ar="التوحيد ...", cited_ids=[])
    out, fake = run({"analyze": analysis(asks_term_meaning=True, asked_term="التوحيد"), "route": routing("A"),
                     "generate": [gdraft, gdraft]}, messages=msgs)
    gen_prompt = [m for s, m in fake.calls if s == "generate"][0][1][1]
    gid = next(line.split("]")[0][3:] for line in gen_prompt.splitlines() if line.startswith("- [GL:"))
    assert "retrieve:glossary_only" in out["trace"] and gid.startswith("GL:")


def test_glossary_citation_is_accepted(monkeypatch):
    monkeypatch.setattr(settings, "ABSTAIN_THRESHOLD", 0.95)
    msgs = [{"role": "seeker", "text": "What does Tawhid mean?"}]
    from retrieval.glossary import glossary_for
    from agent.nodes import gl_id
    gid = gl_id(glossary_for(["Tawhid"], "en")[0])
    gdraft = draft(reply="Tawhid means ...", reply_ar="التوحيد ...", cited_ids=[gid])
    out, _ = run({"analyze": analysis(asks_term_meaning=True, asked_term="التوحيد"), "route": routing("A"), "generate": gdraft},
                 messages=msgs)
    assert out["status"] == "ok" and out["citations"][0]["type"] == "glossary"


def test_level_c_without_evidence_refers_to_specialist(monkeypatch):
    monkeypatch.setattr(settings, "ABSTAIN_THRESHOLD", 0.95)
    out, fake = run({"analyze": analysis(), "route": routing("C")},
                    messages=[{"role": "seeker", "text": "Is it true that Islam kills people who leave it?"}])
    assert out["status"] == "refer" and out["reply"] == templates.REFER_SPECIALIST["en"]
    assert "generate" not in fake.stages()


def test_arabic_quotation_marks_are_allowed():
    d = draft(reply_ar="معنى «التوحيد» إفراد الله بالعبادة: [[Q:2:144]]")
    out, _ = run({"analyze": analysis(), "route": routing("A"), "generate": d})
    assert out["status"] == "ok" and out["attempts"] == 1


def test_verse_typed_by_model_is_replaced_with_store_text():
    from retrieval.mock import MockRetriever
    verse = MockRetriever().get_verbatim("Q:2:144", "en").text_ar   # text taken from the store, not typed
    d = draft(reply=f"Allah says: «{verse}» — this is the meaning.", cited_ids=["Q:2:144"])
    from agent.nodes import repair_draft
    from retrieval import config as kbc
    if not kbc.VERBATIM_DB.exists():
        pytest.skip("needs the verbatim store (ayah matching)")
    fixed = repair_draft(d, MockRetriever().retrieve(["x"], "en"))
    assert "[[Q:2:144]]" in fixed.reply and verse not in fixed.reply


def test_exact_verse_request_without_evidence_abstains(monkeypatch):
    monkeypatch.setattr(settings, "ABSTAIN_THRESHOLD", 0.95)
    out, fake = run({"analyze": analysis(asks_for_verse=True), "route": routing("C")},
                    messages=[{"role": "seeker", "text": "Which verse mentions smartphones? Give me the exact verse."}])
    assert out["status"] == "abstain" and "retrieve:no_verse" in out["trace"]


# ---- second verification layer (independent LLM judge, VERIFY_LLM_JUDGE=1) ----
def test_judge_rejection_is_retried_with_its_issues(monkeypatch):
    from agent.state import Judgement
    monkeypatch.setattr(settings, "VERIFY_LLM_JUDGE", True)
    bad = Judgement(grounded=False, contradicts=True, issues=["Remove the claim X — the evidence says the opposite"])
    out, fake = run({"analyze": analysis(), "route": routing("A"), "generate": draft(),
                     "judge": [bad, Judgement(grounded=True)]})
    assert out["status"] == "ok" and out["attempts"] == 2
    second_prompt = str([m for s, m in fake.calls if s == "generate"][1])
    assert "Remove the claim X" in second_prompt


def test_judge_rejecting_twice_gives_unverified(monkeypatch):
    from agent.state import Judgement
    monkeypatch.setattr(settings, "VERIFY_LLM_JUDGE", True)
    out, _ = run({"analyze": analysis(), "route": routing("A"), "generate": draft(),
                  "judge": Judgement(grounded=False, contradicts=True, issues=["contradicts the evidence"])})
    assert out["status"] == "unverified" and out["note_for_dai"].startswith("⚠")


def test_judge_down_is_fail_open_but_visible(monkeypatch):
    monkeypatch.setattr(settings, "VERIFY_LLM_JUDGE", True)
    out, _ = run({"analyze": analysis(), "route": routing("A"), "generate": draft(),
                  "judge": RuntimeError("endpoint down")})
    assert out["status"] == "ok"
    assert "verify:judge_unavailable" in out["trace"] and out["note_for_dai"].startswith("ℹ️")


def test_unsupported_detail_is_advisory_not_blocking(monkeypatch):
    from agent.state import Judgement
    monkeypatch.setattr(settings, "VERIFY_LLM_JUDGE", True)
    out, fake = run({"analyze": analysis(), "route": routing("A"), "generate": draft(),
                     "judge": Judgement(grounded=False, issues=["the date is not in the evidence"])})
    assert out["status"] == "ok" and out["attempts"] == 1          # no retry, not hidden
    assert any("not in the evidence" in i for i in out["issues"]) and out["note_for_dai"].startswith("🔎")


def test_garbled_draft_is_retried():
    noisy = draft(reply_ar="المسلمون لا يعبدون الكعبة وقد Exploration… Stem sorry. [[Q:2:144]]")
    out, fake = run({"analyze": analysis(), "route": routing("A"), "generate": [noisy, draft()]})
    assert out["status"] == "ok" and out["attempts"] == 2
    assert any("garbled" in i for i in out["retry_issues"])
