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


MAX_SPAN = 8  # longest run of consecutive ayahs one quotation is matched against


@dataclass
class AyahMatch:
    ref_id: str  # "Q:112:1", or "Q:81:19-21" when the quote spans several ayahs
    similarity: float  # 0-1, on normalized text
    is_exact: bool  # quote matches the ayah text exactly (ignoring diacritics)
    quoted: str  # the snippet that was matched


class _AyahIndex:
    def __init__(self):
        rows = list(get_store().iter_ayahs())
        self.refs: list[tuple[int, int]] = [(s, a) for s, a, _, _ in rows]
        self.texts: list[str] = [self._key(t) for _, _, t, _ in rows]

    @staticmethod
    def _key(text: str) -> str:
        # Search key: normalized letters only; ignore punctuation, ayah markers and digits.
        return re.sub(r"\s+", " ", re.sub(r"[^\u0621-\u064a ]+", " ", norm(text))).strip()

    def window(self, start: int, length: int) -> str | None:
        """Text of `length` consecutive ayahs from `start`, if they are in one surah."""
        end = start + length - 1
        if start < 0 or end >= len(self.refs) or self.refs[start][0] != self.refs[end][0]:
            return None
        return " ".join(self.texts[start:end + 1])


@lru_cache(maxsize=1)
def _index() -> _AyahIndex:
    return _AyahIndex()


def _fine_score(query: str, text: str) -> float:
    """Similarity of the quote to the best-aligned part of `text` (0-1)."""
    if len(query) < len(text):
        align = fuzz.partial_ratio_alignment(query, text)
        if align:
            text = text[align.dest_start:align.dest_end]
    return fuzz.ratio(query, text) / 100


def match_ayah(text: str, threshold: float = DEFAULT_THRESHOLD) -> AyahMatch | None:
    """Return the closest ayah (or run of consecutive ayahs) to `text`, or None."""
    idx = _index()
    query = _AyahIndex._key(text)
    if len(query) < MIN_CHARS:
        return None
    # Coarse pass: the ayahs that best contain part of the quote.
    cands = process.extract(query, idx.texts, scorer=fuzz.partial_ratio, limit=8)
    best: tuple[float, int, int] | None = None  # (score, start, length)
    for _, _, i in cands:
        for length in range(1, MAX_SPAN + 1):
            # Every window of this length that contains candidate ayah i.
            for start in range(i - length + 1, i + 1):
                window = idx.window(start, length)
                if window is None:
                    continue
                score = _fine_score(query, window)
                # Prefer the higher score; on a tie, the shorter span.
                if best is None or score > best[0] + 1e-9:
                    best = (score, start, length)
            if len(" ".join(idx.texts[i:i + length])) > len(query) * 1.3:
                break  # longer windows cannot fit the quote better
    if best is None or best[0] < threshold:
        return None
    score, start, length = best
    s, a1 = idx.refs[start]
    a2 = idx.refs[start + length - 1][1]
    ref = f"Q:{s}:{a1}" if length == 1 else f"Q:{s}:{a1}-{a2}"
    return AyahMatch(ref_id=ref, similarity=round(score, 3), is_exact=score >= 0.995, quoted=text.strip())


_VERSE_BRACKETS = re.compile(r"﴿([^﴾]+)﴾")
_OTHER_QUOTES = re.compile(r"«([^»]+)»|\"([^\"]+)\"|“([^”]+)”|\(([^)]{12,})\)")
_REFERENCE = re.compile(r"\[[^\]]{1,40}\]")  # "[البقرة: 144]" next to a quote


def find_quran_quotes(message: str, threshold: float = DEFAULT_THRESHOLD) -> list[AyahMatch]:
    """Find ayah-like quotations inside a free-text message.

    Quran brackets ﴿﴾ are read first, each on its own; then other quotes (« » "" “”
    and long parentheses) in the remaining text. References like "[البقرة: 144]" are
    ignored, so a surah name is never compared as if it were part of a verse. With no
    quotes at all, each Arabic sentence is checked.
    """
    spans = [m.group(1) for m in _VERSE_BRACKETS.finditer(message)]
    rest = _REFERENCE.sub(" ", _VERSE_BRACKETS.sub(" ", message))
    spans += [next(g for g in m.groups() if g) for m in _OTHER_QUOTES.finditer(rest)]
    if not spans:
        spans = [p for p in re.split(r"[.!?؟،,\n:؛]+", rest) if p.strip()]
    found: list[AyahMatch] = []
    for span in spans:
        span = _REFERENCE.sub(" ", span)
        if len(re.findall(r"[\u0621-\u064a]", strip_diacritics(span))) < MIN_CHARS:
            continue
        m = match_ayah(span, threshold)
        if m and all(m.ref_id != f.ref_id for f in found):
            found.append(m)
    return found
