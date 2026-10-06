"""Grounded meaning vs. personalised wording (agent/nodes.py generate + verify), offline.

The model must not invent religious content nor paste the sources; it re-expresses the
sources' meaning for this seeker, in the seeker's language. Mock retriever + scripted LLM.
"""
from __future__ import annotations

import pytest

from agent import llm, settings
from agent.graph import suggest
from agent.state import GroundedPoint, Judgement
from retrieval import config as kb
from tests.agent_fakes import FakeLLM, analysis, draft, routing

EN = [{"id": "m1", "role": "seeker", "text": "Why do Muslims worship the Kaaba? I'm a Christian, just curious."}]
AR = [{"id": "m1", "role": "seeker", "text": "لماذا يعبد المسلمون الكعبة؟ أنا مسيحي وأسأل بفضول."}]
# One sentence copied from the Bayyinat passage of the mock evidence (an explanation, not scripture).
COPIED_AR = ("استقبال المسلمين للكعبة في الصلاة ليس عبادة لها إذ المسلمون لا يعبدون إلا الله وحده وإنما جعل الله "
             "تعالى الكعبة الوجهة [[Q:2:144]]")


@pytest.fixture(autouse=True)
def mock_world(monkeypatch):
    monkeypatch.setattr(kb, "RETRIEVER", "mock")
    monkeypatch.setattr(settings, "VERIFY_LLM_JUDGE", False)
    monkeypatch.setattr(settings, "MAX_DRAFT_ATTEMPTS", 2)
    monkeypatch.setattr(settings, "ABSTAIN_THRESHOLD", 0.35)
    yield
    llm.set_llm_factory(None)


def run(script, messages=EN, **kw):
    fake = FakeLLM(script)
    llm.set_llm_factory(fake)
    return suggest(messages, **kw), fake


def prompt_of(fake, stage, n=0):
    """The n-th prompt sent to a stage, as plain text (system + user)."""
    return "\n".join(text for _, text in [m for s, m in fake.calls if s == stage][n])


# ---- quotation integrity ------------------------------------------------------------
@pytest.mark.parametrize("messages,lang", [(EN, "en"), (AR, "ar")])
def test_quran_text_comes_only_from_the_store_in_any_language(messages, lang):
    from retrieval.mock import MockRetriever
    reply_ar = "المسلمون لا يعبدون الكعبة، بل يستقبلونها في الصلاة امتثالًا لأمر الله: [[Q:2:144]]"
    d = draft(reply=reply_ar if lang == "ar" else draft().reply, reply_ar=reply_ar)
    out, _ = run({"analyze": analysis(language=lang), "route": routing("A"), "generate": d}, messages)
    assert out["status"] == "ok" and out["analysis"]["language"] == lang
    assert MockRetriever().get_verbatim("Q:2:144", lang).text_ar in out["reply"]
    assert "[[" not in out["reply"]


# ---- no fabricated / unsupported claims ------------------------------------------------
def test_a_point_without_a_source_is_rejected_then_unverified():
    unsourced = draft(points=[GroundedPoint(meaning="The Kaaba was built by angels.", source_ids=[])])
    out, _ = run({"analyze": analysis(), "route": routing("A"), "generate": unsourced})
    assert out["status"] == "unverified"
    assert any("has no source" in i for i in out["retry_issues"])


def test_a_point_citing_an_id_outside_the_evidence_is_rejected():
    invented = draft(points=[GroundedPoint(meaning="A hadith says so.", source_ids=["H:bukhari:7"])])
    out, fake = run({"analyze": analysis(), "route": routing("A"), "generate": [invented, draft()]})
    assert out["status"] == "ok" and out["attempts"] == 2
    assert "not in the evidence" in prompt_of(fake, "generate", 1)


def test_point_sources_become_citations():
    d = draft(cited_ids=(), points=[GroundedPoint(meaning="Worship is for God alone; the Kaaba is the direction.",
                                                  source_ids=["QA:bayyinat:9"])])
    out, _ = run({"analyze": analysis(), "route": routing("A"), "generate": d})
    assert "QA:bayyinat:9" in {c["id"] for c in out["citations"]}


def test_unsupported_interpretation_flagged_by_the_judge_is_blocked(monkeypatch):
    monkeypatch.setattr(settings, "VERIFY_LLM_JUDGE", True)
    bad = Judgement(grounded=False, contradicts=True, issues=["The draft adds an interpretation the evidence does not make"])
    out, fake = run({"analyze": analysis(), "route": routing("A"), "generate": draft(),
                     "judge": [bad, Judgement(grounded=True)]})
    assert out["attempts"] == 2 and "interpretation" in prompt_of(fake, "generate", 1)


# ---- natural wording: explanations are re-expressed, not pasted ----------------------
def test_copied_source_sentence_is_rejected_and_rewritten():
    pasted = draft(reply=COPIED_AR, reply_ar=COPIED_AR)
    out, fake = run({"analyze": analysis(language="ar"), "route": routing("A"), "generate": [pasted, draft(
        reply="سؤالك في محله! نحن لا نعبد الكعبة، وإنما نتجه إليها في الصلاة لأن الله أمرنا بذلك: [[Q:2:144]]",
        reply_ar="سؤالك في محله! نحن لا نعبد الكعبة، وإنما نتجه إليها في الصلاة لأن الله أمرنا بذلك: [[Q:2:144]]")]},
        AR)
    assert out["status"] == "ok" and out["attempts"] == 2
    assert "verbatim" in prompt_of(fake, "generate", 1) and "QA:bayyinat:9" in prompt_of(fake, "generate", 1)


def test_reexpressed_meaning_passes():
    from agent.nodes import check_draft
    from retrieval.mock import MockRetriever
    ev = MockRetriever().retrieve(["x"], "ar")
    d = draft(reply="ببساطة: نحن نتجه إلى الكعبة في صلاتنا لأن الله أمرنا بذلك، أما العبادة فهي لله وحده. [[Q:2:144]]",
              reply_ar="ببساطة: نحن نتجه إلى الكعبة في صلاتنا لأن الله أمرنا بذلك، أما العبادة فهي لله وحده. [[Q:2:144]]")
    assert check_draft(d, ev, "ar", "A") == []


# ---- language: the target message, not the sources --------------------------------
def test_english_seeker_with_arabic_sources_gets_english():
    out, fake = run({"analyze": analysis(language="ar"), "route": routing("A"), "generate": draft()})
    # mock evidence is Arabic-only; the analyzer even guessed "ar": the resolver decides "en"
    assert out["analysis"]["language"] == "en" and out["analysis"]["language_source"] == "target_message"
    assert "Write the reply in: en" in prompt_of(fake, "generate")


def test_reply_in_the_sources_language_is_rejected():
    arabic_reply = draft(reply="المسلمون لا يعبدون الكعبة بل يستقبلونها في الصلاة امتثالًا لأمر الله: [[Q:2:144]]")
    out, fake = run({"analyze": analysis(), "route": routing("A"), "generate": [arabic_reply, draft()]})
    assert out["attempts"] == 2 and "must be written in 'en'" in prompt_of(fake, "generate", 1)


def test_arabic_seeker_gets_arabic_even_with_english_translations():
    reply = "سؤال جميل! نحن لا نعبد الكعبة، بل نتجه إليها في الصلاة امتثالًا لأمر الله: [[Q:2:144]]"
    out, fake = run({"analyze": analysis(language="en"), "route": routing("A"),
                     "generate": draft(reply=reply, reply_ar=reply)}, AR)
    assert out["analysis"]["language"] == "ar" and "Write the reply in: ar" in prompt_of(fake, "generate")


# ---- personalisation is about HOW, given the person -----------------------------------
def test_generator_sees_the_seekers_words_and_profile():
    out, fake = run({"analyze": analysis(knowledge_level="beginner", tone="curious", background="Christian"),
                     "route": routing("A"), "generate": draft()})
    p = prompt_of(fake, "generate")
    assert "I'm a Christian, just curious." in p                     # their own words
    assert "knowledge_level=beginner" in p and "background=Christian" in p and "tone=curious" in p
    assert "never for WHAT is true" in p                              # personalisation guardrail


def test_system_prompt_separates_meaning_from_wording():
    from agent.prompts import load
    s = load("generate")
    assert "WHAT to say" in s and "HOW to say it" in s
    assert "never copy their sentences" in s and "do not fill the gap" in s


# ---- message mode: the picked message is the question --------------------------------
def test_message_mode_answers_the_picked_message_only():
    msgs = [{"id": "a", "role": "seeker", "text": "Why do Muslims face the Kaaba when they pray?"},
            {"id": "b", "role": "dai", "text": "Good question, let me explain."},
            {"id": "c", "role": "seeker", "text": "عندي سؤال آخر: لماذا يصوم المسلمون شهر رمضان؟"}]
    out, fake = run({"analyze": analysis(), "route": routing("A"), "generate": draft()}, msgs,
                    reply_mode="message", target_message_id="a")
    p = prompt_of(fake, "generate")
    assert out["analysis"]["language"] == "en"
    assert "Why do Muslims face the Kaaba" in p and "رمضان" not in p   # later message not in context


def test_conversation_mode_answers_the_latest_seeker_message():
    msgs = [{"role": "seeker", "text": "Why do Muslims face the Kaaba when they pray?"},
            {"role": "seeker", "text": "عندي سؤال آخر: لماذا يتجه المسلمون إلى الكعبة في الصلاة؟"}]
    reply = "سؤال جميل! نحن نتجه إلى الكعبة في الصلاة امتثالًا لأمر الله: [[Q:2:144]]"
    out, fake = run({"analyze": analysis(), "route": routing("A"),
                     "generate": draft(reply=reply, reply_ar=reply)}, msgs)
    assert out["analysis"]["language"] == "ar"
    assert "Message you are answering" in prompt_of(fake, "generate")


# ---- insufficient sources ------------------------------------------------------------------
def test_insufficient_sources_abstain_without_generation(monkeypatch):
    monkeypatch.setattr(settings, "ABSTAIN_THRESHOLD", 0.99)
    out, fake = run({"analyze": analysis(), "route": routing("B")})
    assert out["status"] == "abstain" and "generate" not in fake.stages() and out["citations"] == []


def test_textbook_register_gets_one_rewrite_but_is_never_blocked():
    stiff = ("Some people raise questions about this. Scholars have explained that Muslims face the Kaaba "
             "as God commanded: [[Q:2:144]]")
    out, fake = run({"analyze": analysis(), "route": routing("A"), "generate": [draft(reply=stiff), draft()]})
    assert out["status"] == "ok" and out["attempts"] == 2 and "textbook" in prompt_of(fake, "generate", 1)
    # still stiff after the rewrite: accepted (style is not a safety issue)
    out, _ = run({"analyze": analysis(), "route": routing("A"), "generate": draft(reply=stiff)})
    assert out["status"] == "ok"


def test_unresolved_language_is_decided_by_the_analyzer():
    msgs = [{"id": "1", "role": "seeker", "text": "ok?"}]       # nothing reliable, no fallbacks
    reply = "Kami tidak menyembah Ka'bah; kami menghadap ke sana dalam salat karena perintah Allah: [[Q:2:144]]"
    out, _ = run({"analyze": analysis(language="id"), "route": routing("A"),
                  "generate": draft(reply=reply)}, msgs)
    assert out["analysis"]["language"] == "id" and out["analysis"]["language_source"] == "analyzer"
