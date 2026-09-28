"""Extract clean Arabic text from InDesign-made PDFs such as the Bayyinat book.

Such PDFs store some Arabic ligatures (lam-alef, "في", "لله") with their
components in visual order, so naive extraction gives "اإلسالم" for "الإسلام",
"اهلل" for "الله" and "يف" for "في". The misplaced components share the
glyph origin of the preceding character, which lets us detect and reorder them
exactly instead of guessing with word lists.

Quran verses in the book are drawn with glyph fonts (QCF_*) that carry no
Unicode text; those glyphs are dropped and marked with QURAN_GAP so the caller
can put the real verse text back from the verbatim store.
"""
from __future__ import annotations

import re

import pymupdf

QURAN_GAP = "⁣"  # invisible separator marking dropped Quran glyphs
_DIAC = set(chr(c) for c in [*range(0x610, 0x61B), *range(0x64B, 0x660), 0x670])
_ALEFS = set("اأإآ")
_DROP_FONTS = ("QCF", "fotograami", "AGA-Arabesque")
_QURAN_FONTS = ("QCF",)
_SYMBOL_FONTS = ("KFGQPCArabicSymbols",)
_ICON_FONTS = ("(AH)-Manal-High", "adwaassalaf-Bold")
_ICON_SPANS = {"3", "f"}


def _units(chars: list[dict]) -> list[dict]:
    """Group each base character with its following diacritics."""
    units: list[dict] = []
    for c in chars:
        if c["c"] in _DIAC and units:
            units[-1]["text"] += c["c"]
        else:
            units.append({"base": c["c"], "text": c["c"], "x": c["origin"][0],
                          "w": c["bbox"][2] - c["bbox"][0]})
    return units


def _misplaced(units: list[dict], i: int) -> bool:
    """A ligature component: zero-width, or drawn at the previous glyph's origin."""
    u = units[i]
    return u["w"] < 0.05 or (i > 0 and abs(u["x"] - units[i - 1]["x"]) < 0.05)


def _fix_ligatures(units: list[dict]) -> list[dict]:
    out: list[dict] = []
    i, n = 0, len(units)
    while i < n:
        b = units[i]["base"]
        nxt = units[i + 1]["base"] if i + 1 < n else ""
        if (b == "ه" and nxt == "ل" and i + 2 < n and units[i + 2]["base"] == "ل"
                and _misplaced(units, i) and _misplaced(units, i + 1)):
            out += [units[i + 2], units[i + 1], units[i]]  # "لله": [ه, ل] + ل -> ل, ل, ه
            i += 3
        elif b in _ALEFS and nxt == "ل" and _misplaced(units, i):
            out += [units[i + 1], units[i]]  # lam-alef: [ا] + ل -> ل, ا
            i += 2
        elif b == "ي" and nxt == "ف" and _misplaced(units, i):
            out += [units[i + 1], units[i]]  # "في": [ي] + ف -> ف, ي
            i += 2
        else:
            out.append(units[i])
            i += 1
    return out


_LEAD_MARKS = re.compile("^([\u064b-\u0652\u0670.:،؛!؟,]+)\\s*")
_LAFZ_DIAC = re.compile("ال([\u064b-\u0652]+)له")  # "الَله" -> "اللهَ"
_NB = "(?<![\u0621-\u064a\u064b-\u0652])"  # not preceded by a letter or haraka
_NA = "(?![ء-ي])"  # not followed by a letter
# Fallback fixes for ligatures whose glyph did not share an origin. Each pattern
# is impossible in correct Arabic, so replacing it cannot damage good text.
_TEXT_FIXES = [
    (re.compile("ا([إأآ])ل"), r"ال\1"),  # "اإلسالم" -> "الإسلام"
    (re.compile("اهلل"), "الله"),
    (re.compile(_NB + "هللا"), "الله"),  # fully reversed "الله"
    (re.compile(_NB + "([وفب]?)هلل"), r"\1لله"),
    (re.compile(_NB + "([وف]?)يف" + _NA), r"\1في"),
    (re.compile(_NB + "([وف]?)ال([ً-ْ]*)(?=\\s)"), r"\1لا\2"),  # lone "ال" -> "لا"
    # word-final "لً" must carry its alef: "فضلً" -> "فضلًا"
    (re.compile("لً(?=[\\s،.؛:»)]|$)"), "لًا"),
    # lone "لَ" / "وَلَ" (not preceded by a letter or a haraka) -> "لَا"
    (re.compile("(?<![ء-يً-ْ])([وف][ً-ْ]*)?لَ(?=[\\s»،.؛:])"), r"\1لَا"),
]


def fix_text(text: str) -> str:
    for pattern, repl in _TEXT_FIXES:
        text = pattern.sub(repl, text)
    return text


def _tidy_line(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text).strip()
    # In RTL lines the final punctuation/diacritic is extracted first: move it back.
    m = _LEAD_MARKS.match(text)
    if m and len(text) > len(m.group(0)):
        text = text[m.end():] + m.group(1)
    return _LAFZ_DIAC.sub(r"الله\1", fix_text(text))


def page_lines(page: pymupdf.Page) -> list[str]:
    """Return the repaired text lines of a page in reading order."""
    raw = page.get_text("rawdict")
    lines: list[tuple[float, float, str]] = []
    for block in raw["blocks"]:
        for line in block.get("lines", []):
            parts: list[str] = []
            chars: list[dict] = []

            def flush() -> None:
                if chars:
                    parts.append("".join(u["text"] for u in _fix_ligatures(_units(chars))))
                    chars.clear()

            for span in line["spans"]:
                font = span["font"]
                if font.startswith(_QURAN_FONTS):
                    flush()
                    if span["chars"] and (not parts or parts[-1] != QURAN_GAP):
                        parts.append(QURAN_GAP)
                    continue
                if font.startswith(_DROP_FONTS):
                    continue
                span_text = "".join(c["c"] for c in span["chars"]).strip()
                if span_text in _ICON_SPANS and font.startswith(_ICON_FONTS):
                    continue  # decorative bullets drawn with digits/letters
                for c in span["chars"]:  # fix ligatures across span boundaries
                    if ord(c["c"]) < 0x20:
                        continue
                    if font.startswith(_SYMBOL_FONTS) and c["c"].isascii() and c["c"].isalpha():
                        continue  # honorific glyphs (e.g. عليه السلام) with no reliable Unicode
                    chars.append(c)
            flush()
            text = _tidy_line("".join(parts))
            if text:
                y = round(line["bbox"][1], 0)
                lines.append((y, -line["bbox"][2], text))
    # Top-to-bottom, then right-to-left for fragments on the same baseline.
    lines.sort()
    merged: list[str] = []
    last_y = None
    for y, _, text in lines:
        if last_y is not None and abs(y - last_y) <= 2 and merged:
            merged[-1] = f"{merged[-1]} {text}"
        else:
            merged.append(text)
        last_y = y
    return merged
