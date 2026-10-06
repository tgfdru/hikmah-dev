"""Reply-language resolution (agent/language.py) — the single source of truth.

Uses the offline fastText model of the knowledge layer; skipped if it is not built.
"""
from __future__ import annotations

import pytest

from agent.language import resolve_response_language as resolve
from retrieval import config

pytestmark = pytest.mark.skipif(not (config.MODELS_DIR / "lid.176.ftz").exists(),
                                reason="language-id model not downloaded")

AR_Q = "لماذا يتوجه المسلمون إلى الكعبة في صلاتهم؟"
AR_Q2 = "عندي سؤال ثاني، لماذا الصلاة مهمة في الإسلام؟"
EN_Q = "Why is Jesus considered a prophet in Islam?"
EN_Q2 = "Why does Islam prohibit alcohol?"
DAI_AR = "أهلًا بك، سؤال جميل وسأجيبك عنه بإذن الله."


def S(i, text):
    return {"id": str(i), "role": "seeker", "text": text}


def D(i, text):
    return {"id": str(i), "role": "dai", "text": text}


# ---- MODE message: the picked message decides ------------------------------------
def test_1_arabic_conversation_arabic_selected():
    msgs = [S(1, AR_Q), D(2, DAI_AR), S(3, AR_Q2)]
    assert resolve(msgs, "message", "3").language == "ar"


def test_2_arabic_conversation_english_selected():
    msgs = [S(1, AR_Q), D(2, DAI_AR), S(3, EN_Q), S(4, AR_Q2)]
    d = resolve(msgs, "message", "3")
    assert (d.language, d.source, d.target_index) == ("en", "target_message", 2)


def test_3_english_conversation_arabic_selected():
    msgs = [S(1, EN_Q), D(2, "Thanks for asking!"), S(3, AR_Q), S(4, EN_Q2)]
    assert resolve(msgs, "message", "3").language == "ar"


@pytest.mark.parametrize("target,expected", [("2", "en"), ("3", "ar"), ("4", "en")])
def test_4_5_mixed_conversation_selected_message_wins(target, expected):
    msgs = [S(1, "كيف حالك؟"), S(2, EN_Q), S(3, AR_Q2), S(4, EN_Q2)]
    assert resolve(msgs, "message", target).language == expected


def test_6_previous_arabic_ai_reply_does_not_override_english_selection():
    msgs = [S(1, AR_Q), D(2, DAI_AR + " " + DAI_AR), S(3, EN_Q)]
    assert resolve(msgs, "message", "3").language == "en"


def test_7_app_and_profile_language_never_override_a_detected_message():
    msgs = [S(1, AR_Q), S(2, EN_Q)]
    d = resolve(msgs, "message", "2", conversation_lang="ar", profile_lang="ar")
    assert d.language == "en" and d.source == "target_message"


def test_8_short_selected_message_uses_its_context():
    # "Why?" alone is not identifiable; the seeker's neighbouring message is English.
    msgs = [S(1, AR_Q), D(2, DAI_AR), S(3, EN_Q2), D(4, "Because it harms the mind."), S(5, "Why?")]
    d = resolve(msgs, "message", "5")
    assert (d.language, d.source) == ("en", "nearby_message")


def test_9_short_selected_message_without_context_falls_back():
    msgs = [S(1, "نعم"), D(2, "حسنًا")]
    d = resolve(msgs, "message", "1", conversation_lang="ar")
    assert (d.language, d.source) == ("ar", "conversation")
    d = resolve(msgs, "message", "1", profile_lang="ur")
    assert (d.language, d.source) == ("ur", "profile")


# ---- MODE conversation: the latest meaningful seeker message ----------------------
def test_10_arabic_then_english_latest_is_english():
    assert resolve([S(1, "مرحباً، عندي سؤال عن الإسلام."), S(2, EN_Q2)]).language == "en"


def test_11_english_then_arabic_latest_is_arabic():
    assert resolve([S(1, EN_Q2), S(2, AR_Q2)]).language == "ar"


def test_12_ar_en_ar_latest_arabic():
    assert resolve([S(1, AR_Q), S(2, EN_Q), S(3, AR_Q2)]).language == "ar"


def test_13_ar_en_latest_english():
    assert resolve([S(1, AR_Q), D(2, DAI_AR), S(3, EN_Q), S(4, EN_Q2)]).language == "en"


def test_14_latest_too_short_uses_recent_meaningful_messages():
    d = resolve([S(1, AR_Q), S(2, EN_Q), S(3, EN_Q2), S(4, "Okay")])
    assert (d.language, d.source) == ("en", "recent_messages")


def test_14b_recent_tie_goes_to_the_most_recent():
    d = resolve([S(1, EN_Q), S(2, AR_Q2), S(3, "ok")])
    assert d.language == "ar"


def test_15_no_reliable_message_uses_conversation_language():
    d = resolve([S(1, "ok"), D(2, "..."), S(3, "yes")], conversation_lang="fr")
    assert (d.language, d.source) == ("fr", "conversation")


def test_16_no_conversation_language_uses_profile():
    d = resolve([S(1, "ok"), S(2, "Why?")], profile_lang="id")
    assert (d.language, d.source) == ("id", "profile")


def test_17_ui_language_is_not_an_input():
    # There is deliberately no app/UI-language parameter; the da'i's own messages are ignored.
    msgs = [D(1, DAI_AR * 3), S(2, EN_Q)]
    assert resolve(msgs).language == "en"


# ---- regression: target selection --------------------------------------------------
def test_24_unrelated_later_messages_are_not_the_target():
    msgs = [S(1, EN_Q), S(2, AR_Q2)]
    d = resolve(msgs, "message", "1")
    assert d.target_index == 0 and d.language == "en"


def test_invalid_targets_are_rejected():
    msgs = [S(1, EN_Q), D(2, "hi")]
    with pytest.raises(ValueError):
        resolve(msgs, "message", "2")      # not a seeker message
    with pytest.raises(ValueError):
        resolve(msgs, "message", "99")     # unknown id


def test_close_languages_add_up_indonesian():
    # fastText alone: ("id", 0.41) — below the threshold; id+ms together are confident.
    d = resolve([S(1, "Mengapa umat Islam menyembah Ka'bah?")])
    assert d.language in ("id", "ms") and d.source == "target_message"
