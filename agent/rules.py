"""Deterministic rules: no LLM, fully unit-tested.

These are the parts of the agent that must behave the same way every time:
placeholder parsing, reference coverage, rendering of verse/hadith text from the
store, the Level-D hint, and the hard checks of the verifier.
"""
from __future__ import annotations

import re

from retrieval.contract import Evidence

# [[Q:2:144]]  [[Q:112:1-4]]  [[H:bukhari:1]]  [[H:dorar:ab12]]
PLACEHOLDER = re.compile(r"\[\[\s*((?:Q|H):[^\]\s]+)\s*\]\]")
_QID = re.compile(r"^Q:(\d{1,3}):(\d{1,3})(?:-(\d{1,3}))?$")

# Quran / hadith quotation marks may appear only in text rendered from the store.
QUOTE_MARKS = re.compile(r"[﴿﴾«»]")

# Level C: phrases that claim a certainty or consensus the evidence does not give.
CERTAINTY_PHRASES = [
    "all muslims agree", "all scholars agree", "there is consensus", "there is a consensus",
    "unanimously agreed", "every scholar", "no scholar disagrees",
    "أجمع المسلمون", "أجمع العلماء", "بإجماع العلماء", "بالإجماع", "لا خلاف بين العلماء", "باتفاق جميع العلماء",
]

# ---- Level-D hint (HANDOFF §5.3): first person AND ruling word AND personal circumstance ----
_FIRST_PERSON = re.compile(
    r"\b(i|i'm|im|my|me|we|our)\b|(?:^|\s)(أنا|انا|لي|زوجي|زوجتي|عندي|أريد|اريد|نحن|ابني|ابنتي|أبي|أمي)(?:\s|$|[،,.؟?])|"
    r"(?:^|\s)(میں|میرا|میری|میرے|ہم)(?:\s|$)|\b(saya|aku|kami)\b",
    re.IGNORECASE,
)
_RULING = re.compile(
    r"\b(halal|haram|allowed|permissible|permitted|forbidden|sin|sinful|valid|invalid|is it ok|can i|may i|should i)\b|"
    r"(يجوز|حلال|حرام|جائز|يصح|باطل|صحيح شرعا|إثم|اثم|حكم)|(جائز|حرام|حلال|گناہ)|\b(boleh|haram|halal|sah)\b",
    re.IGNORECASE,
)
_CIRCUMSTANCE = re.compile(
    r"\b(marry|married|marriage|wedding|divorce|husband|wife|loan|mortgage|interest|bank|inheritance|will|job|"
    r"salary|business|pray|prayer|fast|fasting|ramadan|zakat|medical|surgery|doctor|abortion|parents?|mother|father|"
    r"convert(ed)?|my country|in (france|germany|uk|usa|america|canada))\b|"
    r"(زواج|زواجي|أتزوج|طلاق|زوج|زوجة|قرض|بنك|فوائد|ربا|ميراث|وصية|عمل|وظيفة|راتب|صلاة|صلاتي|صيام|صومي|زكاة|"
    r"عملية|طبيب|إجهاض|والدي|والدتي|أبي|أمي|البلدية|المحكمة|بلدي|في فرنسا|في أمريكا|في بريطانيا|في ألمانيا)|"
    r"(شادی|طلاق|نماز|روزہ|سود)|\b(nikah|menikah|cerai|riba|sholat|puasa)\b",
    re.IGNORECASE,
)

# Explicit requests for a hadith / prophetic saying.
_HADITH_REQUEST = re.compile(
    r"\bhadith|\bhadeeth|\bahadith|prophet (said|say)|saying of the prophet|sunnah (says|proves)|"
    r"حديث|حديثا|حديثًا|أحاديث|قال رسول الله|قال النبي|حدیث|\bhadis\b",
    re.IGNORECASE,
)


def placeholders(text: str) -> list[str]:
    return PLACEHOLDER.findall(text or "")


def strip_placeholders(text: str) -> str:
    return PLACEHOLDER.sub(" ", text or "")


def level_d_hint(text: str) -> bool:
    """True when the message looks like a personal-ruling request. A hint for the router only."""
    t = text or ""
    return bool(_FIRST_PERSON.search(t) and _RULING.search(t) and _CIRCUMSTANCE.search(t))


def mentions_hadith_request(text: str) -> bool:
    return bool(_HADITH_REQUEST.search(text or ""))


def certainty_claims(text: str) -> list[str]:
    low = (text or "").lower()
    return [p for p in CERTAINTY_PHRASES if p in low]


def _qparts(ref_id: str) -> tuple[int, int, int] | None:
    m = _QID.match(ref_id or "")
    if not m:
        return None
    s, a, b = int(m.group(1)), int(m.group(2)), int(m.group(3) or m.group(2))
    return (s, a, b) if a <= b else None


def is_covered(ref_id: str, allowed: set[str]) -> bool:
    """`ref_id` is one of `allowed`, or a Quran (sub)range inside an allowed range."""
    if ref_id in allowed:
        return True
    q = _qparts(ref_id)
    if not q:
        return False
    for other in allowed:
        o = _qparts(other)
        if o and o[0] == q[0] and o[1] <= q[1] and q[2] <= o[2]:
            return True
    return False


def _quran_label(ref_id: str, lang: str) -> str:
    q = _qparts(ref_id)
    if not q:
        return ref_id
    num = f"{q[0]}:{q[1]}" + (f"-{q[2]}" if q[2] != q[1] else "")
    return {"en": f"Quran {num}", "ur": f"قرآن {num}", "id": f"QS {num}", "fr": f"Coran {num}"}.get(lang, f"Q {num}")


def render(e: Evidence, lang: str) -> str:
    """Exact text from the store. ﴿﴾ only for Quran; hadith in «» with source and grade (HANDOFF §5.1)."""
    if e.type == "quran":
        block = f"﴿{e.text_ar}﴾ [{e.ref}]"
        if lang != "ar" and e.translation:
            block += f"\n“{e.translation}” ({_quran_label(e.id, lang)})"
        return f"\n\n{block}\n\n"
    if e.type == "hadith":
        meta = "، ".join(x for x in [e.source, e.ref, e.grade] if x)
        block = f"«{e.text_ar}» ({meta})"
        if lang != "ar" and e.translation:
            block += f"\n“{e.translation}”"
        return f"\n\n{block}\n\n"
    return f"[{e.ref}]"


def tidy(text: str) -> str:
    text = re.sub(r"[ \t]+\n", "\n", text or "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
