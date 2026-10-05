"""Deterministic rules of the agent (no LLM, no index)."""
from __future__ import annotations

import pytest

from agent import rules
from retrieval.contract import Evidence


@pytest.mark.parametrize("text", [
    "I'm in France, can I marry only at the city hall?",
    "أنا في فرنسا، هل يجوز لي أن أعقد زواجي في البلدية فقط؟",
    "Is it haram for me to take a bank loan with interest for my house?",
    "هل يجوز لي أن أفطر في رمضان بسبب عملي؟",
])
def test_level_d_hint_personal_rulings(text):
    assert rules.level_d_hint(text)


@pytest.mark.parametrize("text", [
    "Can I ask a question?",                       # HANDOFF §5.3 false positive
    "Can I learn about Islam?",
    "Why is alcohol forbidden in Islam?",
    "Why do Muslims worship the Kaaba?",
    "هل القرآن من تأليف محمد؟",
])
def test_level_d_hint_general_questions(text):
    assert not rules.level_d_hint(text)


def test_placeholders_and_strip():
    t = "See [[Q:2:144]] and [[ H:bukhari:1 ]] and [[QA:bayyinat:9]]"
    assert rules.placeholders(t) == ["Q:2:144", "H:bukhari:1"]
    assert "[[" not in rules.strip_placeholders("x [[Q:1:1]] y")


def test_is_covered_ranges():
    allowed = {"Q:112:1-4", "Q:2:144", "QA:bayyinat:9"}
    assert rules.is_covered("Q:112:1", allowed)
    assert rules.is_covered("Q:112:2-3", allowed)
    assert rules.is_covered("Q:2:144", allowed)
    assert not rules.is_covered("Q:2:145", allowed)
    assert not rules.is_covered("Q:112:1-5", allowed)
    assert not rules.is_covered("Q:3:1", allowed)
    assert not rules.is_covered("Q:2:9-1", allowed)


def test_certainty_claims():
    assert rules.certainty_claims("Yes, all Muslims agree on this.")
    assert rules.certainty_claims("وهذا ثابت بالإجماع")
    assert not rules.certainty_claims("Scholars have different views on this.")


def test_hadith_request_keyword():
    assert rules.mentions_hadith_request("Give me a hadith that proves this")
    assert rules.mentions_hadith_request("أعطني حديثًا يثبت ذلك")
    assert not rules.mentions_hadith_request("Why do Muslims pray five times?")


def _ev(**kw):
    base = dict(id="Q:2:144", type="quran", text_ar="نص", translation="Text", source="القرآن الكريم",
                ref="البقرة: 144", grade=None, source_url="u", score=1.0)
    base.update(kw)
    return Evidence(**base)


def test_render_quran_uses_quran_brackets_and_translation():
    out = rules.render(_ev(), "en")
    assert "﴿نص﴾ [البقرة: 144]" in out and "“Text” (Quran 2:144)" in out
    assert "Text" not in rules.render(_ev(), "ar")  # Arabic reader: no translation


def test_render_hadith_never_uses_quran_brackets():
    out = rules.render(_ev(id="H:bukhari:1", type="hadith", source="صحيح البخاري", ref="1", grade="صحيح"), "en")
    assert "﴿" not in out and "«نص»" in out and "صحيح البخاري" in out and "صحيح" in out


def test_render_urdu_translation_without_quotes():
    out = rules.render(_ev(translation="ترجمہ"), "ur")
    assert "“" not in out and "ترجمہ" in out


def test_fallback_client_moves_on_when_model_is_overloaded():
    from agent.llm import _FallbackClient

    class Busy(Exception):
        status_code = 503

    class Bad:
        def invoke(self, m):
            raise Busy("high demand")

    class Good:
        def invoke(self, m):
            return "ok"

    assert _FallbackClient([Bad(), Good()]).invoke([]) == "ok"


def test_fallback_client_does_not_hide_real_errors():
    import pytest as _pt
    from agent.llm import _FallbackClient

    class Broken:
        def invoke(self, m):
            raise ValueError("bad request")

    class Good:
        def invoke(self, m):
            return "ok"

    with _pt.raises(ValueError):
        _FallbackClient([Broken(), Good()]).invoke([])


def test_protocol_per_model_on_opencode_zen(monkeypatch):
    from agent import llm, settings

    monkeypatch.setattr(settings, "AI_BASE_URL", "https://opencode.ai/zen/v1")
    monkeypatch.setattr(settings, "AI_PROTOCOL", "auto")
    assert llm._protocol("gpt-5.4-nano") == "responses"
    assert llm._protocol("claude-haiku-4-5") == "anthropic"
    assert llm._protocol("space-bunny-free") == "chat"
    monkeypatch.setattr(settings, "AI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
    assert llm._protocol("gpt-5.4-nano") == "chat"   # other endpoints: chat unless forced
    monkeypatch.setattr(settings, "AI_PROTOCOL", "responses")
    assert llm._protocol("anything") == "responses"
