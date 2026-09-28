"""Detect Quran quotations in a message and check whether they are quoted correctly.

Challenge test case: "a question that contains a misquoted ayah" -> the assistant
must gently show the correct text with its surah and ayah number.

    m = match_ayah("قل هو الله واحد")
    m.ref_id      -> "Q:112:1"
    m.similarity  -> 0.9  (1.0 = exact after normalization)
    m.is_exact    -> False  => misquote; show get_verbatim(m.ref_id, lang)

The agent should add `m.ref_id` to its evidence so that the verifier accepts the
[[Q:..]] placeholder it produces for the corrected ayah.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from rapidfuzz import fuzz, process

from retrieval.normalize_ar import norm, strip_diacritics
from retrieval.verbatim import get_store

MIN_CHARS = 12  # shorter snippets are too ambiguous to attribute to one ayah
DEFAULT_THRESHOLD = 0.80


@dataclass
class AyahMatch:
    ref_id: str  # "Q:112:1" or "Q:2:255-256" when the quote spans two ayahs
    similarity: float  # 0-1, on normalized text
    is_exact: bool  # quote matches the ayah text exactly (ignoring diacritics)
    quoted: str  # the snippet that was matched


class _AyahIndex:
    def __init__(self):
        rows = list(get_store().iter_ayahs())
        self.refs: list[tuple[int, int]] = [(s, a) for s, a, _, _ in rows]
        self.texts: list[str] = [self._key(t) for _, _, t, _ in rows]
        # Consecutive ayah pairs, for quotes that run across an ayah boundary.
        self.pair_refs = [
            (self.refs[i], self.refs[i + 1])
            for i in range(len(rows) - 1)
            if self.refs[i][0] == self.refs[i + 1][0]
        ]
        pos = {r: i for i, r in enumerate(self.refs)}
        self.pair_texts = [self.texts[pos[a]] + " " + self.texts[pos[b]] for a, b in self.pair_refs]

    @staticmethod
    def _key(text: str) -> str:
        # Search key: normalized letters only; ignore punctuation and Quranic stop marks.
        return re.sub(r"[^ء-ي ]+", "", norm(text)).strip()


@lru_cache(maxsize=1)
def _index() -> _AyahIndex:
    return _AyahIndex()


def _best(query: str, choices: list[str]) -> tuple[int, float]:
    # Coarse pass: partial_ratio finds the ayah that contains the quote.
    cands = process.extract(query, choices, scorer=fuzz.partial_ratio, limit=8)
    best_i, best_s = -1, 0.0
    for _, _, i in cands:
        text = choices[i]
        # Fine pass: compare against the best-aligned window of the ayah.
        if len(query) < len(text):
            align = fuzz.partial_ratio_alignment(query, text)
            window = text[align.dest_start:align.dest_end] if align else text
        else:
            window = text
        s = fuzz.ratio(query, window) / 100
        if s > best_s:
            best_i, best_s = i, s
    return best_i, best_s


def match_ayah(text: str, threshold: float = DEFAULT_THRESHOLD) -> AyahMatch | None:
    """Return the closest ayah to `text`, or None if nothing is similar enough."""
    idx = _index()
    query = _AyahIndex._key(text)
    if len(query) < MIN_CHARS:
        return None
    i, s = _best(query, idx.texts)
    ref = f"Q:{idx.refs[i][0]}:{idx.refs[i][1]}" if i >= 0 else None
    if s < 0.98:  # maybe the quote runs across two ayahs
        j, s2 = _best(query, idx.pair_texts)
        if s2 > s + 0.03:
            (su, a1), (_, a2) = idx.pair_refs[j]
            ref, s = f"Q:{su}:{a1}-{a2}", s2
    if ref is None or s < threshold:
        return None
    return AyahMatch(ref_id=ref, similarity=round(s, 3), is_exact=s >= 0.995, quoted=text.strip())


_QUOTE_SPANS = re.compile(r"﴿([^﴾]+)﴾|«([^»]+)»|\"([^\"]+)\"|“([^”]+)”|\(([^)]{12,})\)")


def find_quran_quotes(message: str, threshold: float = DEFAULT_THRESHOLD) -> list[AyahMatch]:
    """Find ayah-like quotations inside a free-text message.

    Checks explicit quotes first (﴿﴾ «» "" “” and long parentheses); if none,
    checks each Arabic sentence of the message. Returns matches sorted by position.
    """
    spans = [next(g for g in m.groups() if g) for m in _QUOTE_SPANS.finditer(message)]
    if not spans:
        spans = [p for p in re.split(r"[.!?؟،,\n:؛]+", message) if p.strip()]
    found: list[AyahMatch] = []
    for span in spans:
        if len(re.findall(r"[ء-ي]", strip_diacritics(span))) < MIN_CHARS:
            continue
        m = match_ayah(span, threshold)
        if m and all(m.ref_id != f.ref_id for f in found):
            found.append(m)
    return found
