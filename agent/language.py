"""Which language the suggested reply is written in — the single source of truth.

Principle: the reply is in the language of the seeker message the da'i is actually
answering. Not the first message, not the majority of the conversation, not the app or the
da'i's language, not the language of the retrieved sources, and not a previous AI reply.

Two modes (set by the caller, see api/schemas.py):

* ``message`` — the da'i picked a seeker message (``target_message_id``).
    1. that message, when its language is detected confidently;
    2. the nearest seeker messages around it (context of that message);
    3. the latest meaningful seeker message;
    4. the conversation language (given by the site, else the dominant language of the
       seeker's meaningful messages);
    5. the seeker's profile language.
* ``conversation`` — no message picked: the target is the latest seeker message.
    1. that message, when confident;
    2. the recent meaningful seeker messages (dominant language, ties -> most recent);
    3. conversation language; 4. profile language.

"Confident" needs enough text: fastText labels short words ("Yes", "Why?", "Okay")
almost at random and with high scores ("Kenapa?" -> Italian 0.64), so a message counts
only with >= MIN_LETTERS letters and probability >= MIN_PROB (Intercom uses a similar
10-character minimum before trusting detection).
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

MIN_LETTERS = 10       # below this a message is too short to identify its language
MIN_PROB = 0.6
RECENT_WINDOW = 3      # recent seeker messages consulted when the target is ambiguous
NEARBY_WINDOW = 2      # seeker messages on each side of a picked message
DEFAULT_LANGUAGE = "en"
_LETTER = re.compile(r"[^\W\d_]")
SEEKER_ROLES = ("seeker", "user", "beneficiary")


@dataclass(frozen=True)
class LanguageDecision:
    language: str
    source: str          # target_message | nearby_message | recent_messages | conversation | profile | default
    confidence: float
    target_index: int    # index in `messages` of the message being answered (-1 if none)

    def as_dict(self) -> dict:
        return {"language": self.language, "source": self.source, "confidence": round(self.confidence, 3)}


def is_seeker(m: dict) -> bool:
    return str(m.get("role", "seeker")).lower() in SEEKER_ROLES


# fastText splits its probability between close languages ("Mengapa umat Islam menyembah Ka'bah?" ->
# id 0.41 + ms …); their probabilities are added up, and the top label of the group is kept.
_GROUPS = [{"id", "ms"}, {"ur", "fa", "pnb"}, {"ar", "arz", "ary", "acm", "apc", "ajp"}]


def _detect(text: str) -> tuple[str, float] | None:
    try:
        from retrieval.langid import detect_language
    except Exception:  # noqa: BLE001
        return None
    try:
        code, prob = detect_language(text)
    except Exception:  # noqa: BLE001 — model missing: no detection, fall back
        return None
    group = next((g for g in _GROUPS if code in g), None)
    if group and prob < MIN_PROB:
        prob = max(prob, _group_probability(text, group))
    return code, prob


def _group_probability(text: str, group: set[str]) -> float:
    try:
        import re as _re

        from retrieval.langid import _model, _without_quotes
        labels = _model().f.predict(_re.sub(r"\s+", " ", _without_quotes(text)).strip() + "\n", 5, 0.0, "strict")
        return float(sum(p for p, lab in labels if lab.replace("__label__", "") in group))
    except Exception:  # noqa: BLE001
        return 0.0


def detect_confident(text: str) -> tuple[str, float] | None:
    """(language, probability) only when the text is long enough and the detector is sure."""
    text = (text or "").strip()
    if len(_LETTER.findall(text)) < MIN_LETTERS:
        return None
    got = _detect(text)
    if not got or got[1] < MIN_PROB:
        return None
    return got


def target_index(messages: list[dict], mode: str = "conversation", target_id: str | None = None) -> int:
    """Index of the seeker message being answered.

    ``message`` mode: the message with ``id == target_id`` (must be a seeker message).
    ``conversation`` mode: the latest seeker message.
    """
    if mode == "message":
        for i, m in enumerate(messages):
            if target_id is not None and str(m.get("id")) == str(target_id):
                if not is_seeker(m):
                    raise ValueError("target_message_id must point to a seeker message")
                return i
        raise ValueError(f"target_message_id {target_id!r} is not in messages")
    for i in range(len(messages) - 1, -1, -1):
        if is_seeker(messages[i]):
            return i
    return len(messages) - 1 if messages else -1


def _dominant(langs: list[tuple[str, float]]) -> tuple[str, float] | None:
    """Most frequent language; ties go to the most recent (langs are oldest -> newest)."""
    if not langs:
        return None
    counts = Counter(lang for lang, _ in langs)
    top = max(counts.values())
    for lang, prob in reversed(langs):
        if counts[lang] == top:
            return lang, prob
    return None


def conversation_language(messages: list[dict]) -> tuple[str, float] | None:
    """Fallback only: dominant language of the seeker's meaningful messages."""
    return _dominant([d for m in messages if is_seeker(m) and (d := detect_confident(m.get("text", "")))])


def resolve_response_language(messages: list[dict], mode: str = "conversation",
                              target_id: str | None = None,
                              conversation_lang: str | None = None,
                              profile_lang: str | None = None) -> LanguageDecision:
    """Decide the reply language (see the module docstring for the order)."""
    idx = target_index(messages, mode, target_id)
    if idx < 0:
        return LanguageDecision(_norm(conversation_lang or profile_lang) or DEFAULT_LANGUAGE,
                                "conversation" if conversation_lang else ("profile" if profile_lang else "default"),
                                0.0, -1)

    # 1. the message being answered
    got = detect_confident(messages[idx].get("text", ""))
    if got:
        return LanguageDecision(got[0], "target_message", got[1], idx)

    seekers = [i for i, m in enumerate(messages) if is_seeker(m)]
    # 2. message mode: the picked message's neighbours (closest first, earlier wins a tie)
    if mode == "message":
        pos = seekers.index(idx)
        for dist in range(1, NEARBY_WINDOW + 1):
            for j in (pos - dist, pos + dist):
                if 0 <= j < len(seekers):
                    got = detect_confident(messages[seekers[j]].get("text", ""))
                    if got:
                        return LanguageDecision(got[0], "nearby_message", got[1], idx)

    # 3. recent meaningful seeker messages, newest first
    #    message mode: the latest meaningful one; conversation mode: the dominant one among the last few
    recent = [d for i in seekers[::-1] if (d := detect_confident(messages[i].get("text", "")))]
    if recent:
        if mode == "message":
            return LanguageDecision(recent[0][0], "recent_messages", recent[0][1], idx)
        dom = _dominant(list(reversed(recent[:RECENT_WINDOW])))
        if dom:
            return LanguageDecision(dom[0], "recent_messages", dom[1], idx)

    # 4. conversation language (site-provided, else computed), 5. profile language
    if conversation_lang:
        return LanguageDecision(_norm(conversation_lang), "conversation", 0.5, idx)
    conv = conversation_language(messages)
    if conv:
        return LanguageDecision(conv[0], "conversation", conv[1], idx)
    if profile_lang:
        return LanguageDecision(_norm(profile_lang), "profile", 0.5, idx)
    # Last resort: a weak guess from the target itself beats a fixed default.
    weak = _detect(messages[idx].get("text", ""))
    if weak and weak[1] >= 0.5:
        return LanguageDecision(weak[0], "target_message_weak", weak[1], idx)
    return LanguageDecision(DEFAULT_LANGUAGE, "default", 0.0, idx)


def _norm(code: str | None) -> str:
    return (code or "").strip().lower().replace("_", "-").split("-")[0][:3]
