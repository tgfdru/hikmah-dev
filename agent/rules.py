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

# The ornate Quran brackets may appear only in text rendered from the store.
# (« » are ordinary quotation marks in Arabic, so they are allowed; Quran-like text inside
# any quotes is caught by ayah matching in the verifier.)
QUOTE_MARKS = re.compile(r"[﴿﴾]")

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
            # Arabic-script translations (Urdu) are not put in quotation marks, so they are never
            # mistaken for quoted verse text.
            tr = e.translation if lang == "ur" else f"“{e.translation}”"
            block += f"\n{tr} ({_quran_label(e.id, lang)})"
        return f"\n\n{block}\n\n"
    if e.type == "hadith":
        meta = "، ".join(x for x in [e.source, e.ref, e.grade] if x)
        text = e.text_ar if "«" in e.text_ar else f"«{e.text_ar}»"  # HadeethEnc already marks the Prophet's words
        block = f"{text} ({meta})"
        if lang != "ar" and e.translation:
            block += f"\n“{e.translation}”"
        return f"\n\n{block}\n\n"
    return f"[{e.ref}]"


# Evidence ids written into the reply text ("[[GL:5744]]", "([SH:69:7], [QA:bayyinat:138])").
# Only [[Q:..]] / [[H:..]] placeholders belong in the text; other ids go in cited_ids.
RAW_ID = re.compile(r"\[{1,2}\s*(?:GL|SH|QA|BK|Q|H):[^\]]*\]{1,2}")
_RAW_ID_GROUP = re.compile(r"\s*\(\s*(?:\[{1,2}[^\]]*\]{1,2}[\s,،;]*)+\)|\s*\[{1,2}\s*(?:GL|SH|QA|BK):[^\]]*\]{1,2}")


def raw_ids(text: str) -> list[str]:
    """Evidence ids left in the reply text outside [[Q:..]]/[[H:..]] placeholders."""
    return RAW_ID.findall(strip_placeholders(text))


def tidy(text: str) -> str:
    text = _RAW_ID_GROUP.sub("", text or "")  # last-resort cleanup of stray non-scripture ids
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---- garbled output (model noise inside the reply) --------------------------------
# Seen in evaluation: "وقد Exploration…Stem sorry." in the middle of an Arabic reply.
_LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z'’-]+")
_LATIN_RUN = re.compile(r"[A-Za-z][A-Za-z'’-]*(?:[\s.…,;:!?\"'()-]+[A-Za-z][A-Za-z'’-]*)+")
# Scripts no supported reply language uses (CJK, Cyrillic, Hangul, Thai, Devanagari).
_FOREIGN_SCRIPT = re.compile(r"[Ѐ-ӿ฀-๿ऀ-ॿ぀-ヿ㐀-鿿가-힯]")
_IGNORED = re.compile(r"\[\[[^\]]*\]\]|https?://\S+|\b[A-Z]{1,3}:[\w:.-]+")
# Latin letters attached to Arabic letters with no space (seen: "أوshares", "يمكنEnhance").
_GLUED = re.compile(r"[\u0621-\u064a\u0671-\u06d3]+[A-Za-z]+|[A-Za-z]+[\u0621-\u064a\u0671-\u06d3]+")
# Arabic-script replies: how much Latin is acceptable (an approved term or a name is fine).
_LATIN_LIMITS = {"ar": (2, 3), "ur": (3, 6), "fa": (3, 6)}  # (longest run, total words)


def garbled(text: str, lang: str, allowed_words: set[str] | None = None) -> str | None:
    """Return a short description if `text` contains output noise, else None.

    Arabic-script replies may contain a few Latin words (approved glossary terms, names);
    a run of several Latin words or many of them means the model leaked another language.
    Any reply containing an unexpected script (CJK, Cyrillic, …) is noise.
    """
    clean = _IGNORED.sub(" ", text or "")
    m = _FOREIGN_SCRIPT.search(clean)
    if m:
        return f"unexpected characters from another script ({m.group(0)!r})"
    glued = _GLUED.search(clean)
    if glued:  # "أوshares", "الرواياتReachنا": never a term or a name
        return f'Latin letters glued to an Arabic-script word: "{glued.group(0)}"'
    if lang not in _LATIN_LIMITS:
        return None
    allowed = {w.lower() for w in (allowed_words or set())}
    words = [w for w in _LATIN_WORD.findall(clean) if w.lower() not in allowed]
    max_run, max_total = _LATIN_LIMITS[lang]
    runs = [r for r in _LATIN_RUN.findall(clean)
            if len([w for w in _LATIN_WORD.findall(r) if w.lower() not in allowed]) >= max_run]
    if runs:
        return f'Latin text inside the {lang} reply: "{runs[0][:60]}"'
    if len(words) >= max_total:
        return f"{len(words)} Latin words inside the {lang} reply (e.g. {', '.join(words[:4])})"
    return None


# ---- copied source wording -----------------------------------------------------------
# Explanations (Bayyinat, Shamela) must be re-expressed for the seeker, not pasted. A run of
# COPY_RUN or more identical words (after search normalisation) between the draft and an
# explanatory passage means the model copied a sentence. Scripture is never in the draft text
# (placeholders only), so it cannot trigger this.
COPY_RUN = 8
_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    try:
        from retrieval.normalize_ar import norm
        text = norm(text)
    except Exception:  # noqa: BLE001
        text = (text or "").lower()
    return _WORD.findall(text)


def longest_shared_run(a: str, b: str) -> tuple[int, str]:
    """Longest run of consecutive identical words shared by `a` and `b` (length, the words)."""
    ta, tb = _tokens(strip_placeholders(a)), _tokens(b)
    if not ta or not tb:
        return 0, ""
    best, end = 0, 0
    prev = [0] * (len(tb) + 1)
    for i in range(1, len(ta) + 1):
        cur = [0] * (len(tb) + 1)
        wa = ta[i - 1]
        for j in range(1, len(tb) + 1):
            if wa == tb[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best, end = cur[j], i
        prev = cur
    return best, " ".join(ta[end - best:end])


# Languages fastText often confuses with each other; either label is accepted for the other.
_SAME_LANGUAGE = [{"ur", "fa", "pnb"}, {"id", "ms"}, {"ar", "arz", "ary"}]


def same_language(a: str, b: str) -> bool:
    if a == b:
        return True
    return any(a in g and b in g for g in _SAME_LANGUAGE)


# ---- academic / boilerplate register ----------------------------------------------------
# The reply is a chat message from the da'i, not a passage from a book. These openers are the
# sources' register; seen in a real draft ("يثير البعض تساؤلات حول… ويوضح أهل العلم أن…").
# Style is never a reason to block a draft: it triggers one rewrite, then the draft is accepted.
BOILERPLATE = [
    "يثير البعض", "يوضح أهل العلم", "يُوضح أهل العلم", "بين أهل العلم", "ذكر أهل العلم", "قرر أهل العلم",
    "ومما ينبغي التنبيه عليه", "تجدر الإشارة إلى", "والجواب عن هذه الشبهة", "الجواب عن ذلك من وجوه",
    "scholars have explained", "scholars explain that", "it should be noted", "it is worth noting",
    "some people raise questions", "the answer to this doubt", "in conclusion,",
]


def boilerplate(text: str) -> list[str]:
    low = (text or "").lower()
    return [p for p in BOILERPLATE if p.lower() in low]
