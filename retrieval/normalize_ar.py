"""Arabic normalization for indexing and search only.

Text shown to users is never normalized: the verbatim store keeps the original
diacritized text. These functions only produce keys for matching.
"""
from __future__ import annotations

import re
import unicodedata

# Harakat, Quranic annotation marks, superscript alef and tatweel.
_DIACRITICS = re.compile(
    "[ؐ-ًؚ-ٰٟۖ-ۜ۟-۪ۨ-ۭـ]"
)
# Invisible characters that sneak into copied text (BOM, zero-width, bidi marks).
_INVISIBLE = re.compile("[﻿​-‏‪-‮⁦-⁩­]")
_ALEF = re.compile("[آأإٱٲٳ]")  # آ أ إ ٱ ...
_CHAR_MAP = str.maketrans(
    {
        "ى": "ي",  # ى -> ي
        "ة": "ه",  # ة -> ه
        "ؤ": "و",  # ؤ -> و
        "ئ": "ي",  # ئ -> ي
        "ی": "ي",  # Persian/Urdu yeh -> ي
        "ے": "ي",  # Urdu yeh barree -> ي
        "ک": "ك",  # Persian/Urdu kaf -> ك
        "ہ": "ه",  # Urdu heh goal -> ه
    }
)
_ARABIC_LETTER = re.compile("[ء-ي]")
_TOKEN = re.compile(r"[ء-ي]+|[a-z0-9]+")
_AR_PREFIXES = ("وال", "بال", "كال", "فال", "لل", "ال")

_EN_STOP = frozenset(
    "a an the of to in on and or is are was were be been it its this that these those "
    "for with as by at from do does did why what how who whom which when where can could "
    "would should i you he she we they me my your our their his her them us not no so "
    "if then than there about into over also just".split()
)
_AR_STOP = frozenset(
    "في من على الى عن ما ماذا لماذا هل ان او ثم لا لم لن قد كان كانت هو هي هم هذا هذه ذلك "
    "تلك التي الذي الذين كل بعض اي كيف متي اين مع عند بين حتي اذا لكن بل انا نحن انت".split()
)


def strip_diacritics(text: str) -> str:
    return _DIACRITICS.sub("", text)


def norm(text: str) -> str:
    """Normalize Arabic (and lowercase Latin) text for matching."""
    text = unicodedata.normalize("NFKC", text)
    text = _INVISIBLE.sub("", text)
    text = _DIACRITICS.sub("", text)
    text = _ALEF.sub("ا", text)
    text = text.translate(_CHAR_MAP)
    return re.sub(r"\s+", " ", text).strip().lower()


def has_arabic(text: str) -> bool:
    return bool(_ARABIC_LETTER.search(norm(text)))


def _stem_ar(token: str) -> str:
    for prefix in _AR_PREFIXES:
        if token.startswith(prefix) and len(token) - len(prefix) >= 3:
            return token[len(prefix):]
    return token


def tokenize(text: str) -> list[str]:
    """Tokens for BM25: normalized Arabic words (light prefix stemming) + English words."""
    tokens = []
    for tok in _TOKEN.findall(norm(text)):
        if tok in _EN_STOP or tok in _AR_STOP:
            continue
        if _ARABIC_LETTER.match(tok):
            tok = _stem_ar(tok)
        if len(tok) > 1:
            tokens.append(tok)
    return tokens
