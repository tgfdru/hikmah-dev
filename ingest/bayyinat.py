"""Parse the Bayyinat book (Usul Center) into Q&A records for the search index.

    python -m ingest.bayyinat

Input : data/raw/bayyinat/bayyinat.pdf  (official download from dawa.center/file/7937)
Output: data/processed/bayyinat.jsonl

Each of the book's 263 questions becomes:
  QA:bayyinat:<n>        the question, similar phrasings and the book's short answer
                         (مختصر الإجابة) - the best evidence for a draft reply
  QA:bayyinat:<n>:<k>    parts (k = 2, 3, ...) of the detailed answer (الجواب التفصيلي)

Quran verses in the PDF are drawn with glyph fonts and cannot be extracted; the
book always follows them with a reference such as [البقرة: 144], so we put the
exact verse text back from the verbatim store at that reference.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import pymupdf

from ingest.pdf_ar import QURAN_GAP, page_lines
from retrieval import config
from retrieval.normalize_ar import norm, strip_diacritics
from retrieval.verbatim import VerbatimStore

SOURCE = "بينات: أسئلة وأجوبة عن الإسلام (مركز أصول)"
PDF_URL = "https://dawa.center/storage/files/AMYj6DfmHlSnZ766Zz0VlBNwmYtdwhAl31XMETlT.pdf"
BOOK_URL = "https://dawa.center/file/7937"
EXPECTED_QUESTIONS = 263
CHUNK_CHARS = 1400  # detailed-answer chunk size (~300-400 tokens)

TOC_PAGES = range(4, 21)  # 0-based pdf pages holding the table of contents
_TOC_NUM = re.compile(r"(\d{1,3})\(")
_DOTS = re.compile(r"\.{3,}")


def _key(line: str) -> str:
    return re.sub(r"[^ء-ي ]", "", norm(line)).strip()


# Section headings (compared on normalized text).
H_QUESTION = "السوال"
H_SIMILAR = "عبارات مشابهه للسوال"
H_ANSWER = "الجواب"
H_GIST = "مضمون السوال"
H_SUMMARY = "مختصر الاجابه"
H_DETAIL = "الجواب التفصيلي"
H_END = ("كلمات دلاليه", "اسئله ذات علاقه")


@dataclass
class Question:
    n: int
    title: str = ""
    page: int = 0  # 1-based pdf page where the question starts
    question: list[str] = field(default_factory=list)
    similar: list[str] = field(default_factory=list)
    gist: list[str] = field(default_factory=list)
    summary: list[str] = field(default_factory=list)
    detail: list[tuple[int, str]] = field(default_factory=list)  # (page, line)
    keywords: str = ""


def read_pages(doc: pymupdf.Document) -> list[list[str]]:
    pages = []
    for i in range(doc.page_count):
        lines = page_lines(doc[i])
        # Running header: first line carrying the printed page number (= pdf index).
        if lines and re.search(rf"(?<!\d){i}(?!\d)", lines[0]):
            lines = lines[1:]
        pages.append(lines)
    return pages


def parse_toc(pages: list[list[str]]) -> dict[int, str]:
    """{question number: clean title} from the table of contents.

    Entries are numbered 1..263 in order. RTL extraction sometimes splits a number
    ("217" -> "2" + "17("), so a number is accepted only as the next expected one
    (or its last digits), which keeps entries from overwriting each other.
    """
    titles: dict[int, str] = {}
    pending: tuple[int, str] | None = None
    expected = 1
    for p in TOC_PAGES:
        for line in pages[p]:
            if "فهرس" in line or line.strip() in ("المسألة الصفحة", "الصفحة المسألة"):
                continue
            text = _DOTS.sub(" ", line)
            m = next((m for m in _TOC_NUM.finditer(line)
                      if str(expected).endswith(m.group(1))), None)
            if m:
                if pending:  # previous entry had no page line; keep what we have
                    titles[pending[0]] = _clean_title(pending[1])
                n = expected
                expected += 1
                title = text.replace(m.group(0), " ")
                title = re.sub(r"^\s*\d{1,4}\s+|\s+\d{1,4}\s*$", " ", title)  # page number
                title = re.sub(r"-?\)\s*:?|^\s*[-:]\s*", " ", title)
                has_page = bool(re.search(r"(^|\s)\d{1,4}(\s|$)", text.replace(m.group(0), " ")))
                pending = (n, title)
                if has_page:
                    titles[n] = _clean_title(title)
                    pending = None
            elif pending:
                rest = re.sub(r"(^|\s)\d{1,4}(\s|$)", " ", text)
                titles[pending[0]] = _clean_title(pending[1] + " " + rest)
                pending = None
    return titles


def _clean_title(t: str) -> str:
    t = t.replace(QURAN_GAP, " ").replace("﴿", " ").replace("﴾", " ")
    t = re.sub(r"\s+", " ", t).strip(" -.:")
    return t


def split_questions(pages: list[list[str]]) -> list[Question]:
    """Walk the body; a question starts at each standalone "السؤال" heading."""
    flat: list[tuple[int, str]] = [(p + 1, line) for p, lines in enumerate(pages) for line in lines]
    starts = [i for i, (_, line) in enumerate(flat) if _key(line) == H_QUESTION]
    questions: list[Question] = []
    for qi, start in enumerate(starts):
        end = starts[qi + 1] if qi + 1 < len(starts) else len(flat)
        q = Question(n=qi + 1, page=flat[start][0])
        section = "question"
        for page, line in flat[start + 1:end]:
            k = _key(line)
            if k == H_SIMILAR:
                section = "similar"
                continue
            if k == H_ANSWER:
                section = "gist"
                continue
            if k.startswith(H_GIST) and len(k) < len(H_GIST) + 3:
                section = "gist"
                continue
            if k.startswith(H_SUMMARY) and len(k) < len(H_SUMMARY) + 3:
                section = "summary"
                continue
            if k.startswith(H_DETAIL) and len(k) < len(H_DETAIL) + 3:
                section = "detail"
                continue
            if any(k.startswith(h) or k.endswith(h) for h in H_END) or "كلمات دلاليه" in k:
                q.keywords = re.sub(r"(كلماتٌ دلاليَّة|أسئلة ذات علاقة)[،:]*", "", line).strip(" ،:")
                section = "end"
                continue
            if section == "end":
                # Tail of the keyword line, or the next question's title/header lines.
                if len(q.keywords) < 200 and page == (q.detail[-1][0] if q.detail else q.page):
                    q.keywords += " " + line
                continue
            if section == "question":
                q.question.append(line)
            elif section == "similar":
                q.similar.append(line)
            elif section == "gist":
                q.gist.append(line)
            elif section == "summary":
                q.summary.append(line)
            else:
                q.detail.append((page, line))
        questions.append(q)
    return questions


def _trim_next_title(q: Question, next_q: Question | None) -> None:
    """Drop the next question's title/marker lines that sit before its "السؤال" heading."""
    if not next_q:
        return
    body = q.detail or [(q.page, x) for x in q.summary]
    while body and body[-1][0] == next_q.page:
        body.pop()
    if q.detail:
        q.detail = body


_OPEN, _CLOSE = "\ue000", "\ue001"  # sentinels for verses we insert
_VARIANTS = {"ا": "اأإآ", "ه": "هة", "ي": "يى", "و": "وؤ"}


def _fuzzy_name(name_key: str) -> str:
    """Regex for a normalized surah name tolerating harakat and letter variants."""
    parts = []
    for ch in name_key:
        if ch == " ":
            parts.append(r"\s*")
        else:
            parts.append(f"[{_VARIANTS.get(ch, ch)}][\u064b-\u0652]*")
    return "".join(parts)


class QuranFiller:
    """Replace verse references like [البقرة: 144] with the exact verse text."""

    def __init__(self, store: VerbatimStore):
        self.store = store
        names = {_key(store.surah_name(s, "ar")): s for s in range(1, 115)}
        last_words: dict[str, list[int]] = {}
        for k, s in names.items():
            last_words.setdefault(k.split()[-1], []).append(s)
        self.aliases = dict(names)
        for w, ss in last_words.items():  # "عمران" for "آل عمران" split across lines
            if len(ss) == 1 and len(w) >= 3 and w not in self.aliases:
                self.aliases[w] = ss[0]
        alt = "|".join(_fuzzy_name(a) for a in sorted(self.aliases, key=len, reverse=True))
        num = r"(\d{1,3})(?:\s*[-–]\s*(\d{1,3}))?"
        # Normal order "[البقرة: 144]" and the reversed RTL extraction "]144 :[البقرة".
        self.normal = re.compile(rf"\[\s*({alt})\s*:\s*{num}\s*\]")
        self.reverse = re.compile(rf"\]{num}\s*:\s*\[?\s*({alt})(?![\u0621-\u064a])")

    def fill(self, text: str) -> tuple[str, list[str]]:
        refs: list[str] = []
        matches = [(m.start(), m.end(), m.group(1), m.group(2), m.group(3))
                   for m in self.normal.finditer(text)]
        matches += [(m.start(), m.end(), m.group(3), m.group(1), m.group(2))
                    for m in self.reverse.finditer(text)]
        out, last = [], 0
        for start, end, surah, a, b in sorted(matches):
            if start < last:
                continue
            s = self.aliases.get(_key(surah))
            x, y = sorted((int(a), int(b or a)))
            ev = self.store.get_quran(f"Q:{s}:{x}" if x == y else f"Q:{s}:{x}-{y}", "ar") if s else None
            if ev is None:
                continue
            refs.append(ev.id)
            out += [text[last:start], f" {_OPEN}{ev.text_ar}{_CLOSE} [{ev.ref}] "]
            last = end
        out.append(text[last:])
        result = "".join(out)
        # Drop the book's now-empty glyph brackets, then restore ours.
        result = re.sub(f"[{QURAN_GAP}﴿﴾]", " ", result)
        result = result.replace(_OPEN, "﴿").replace(_CLOSE, "﴾")
        return re.sub(r"\s+", " ", result).strip(), refs


def _join(lines: list[str]) -> str:
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def _chunks(lines: list[tuple[int, str]], size: int = CHUNK_CHARS) -> list[tuple[int, str]]:
    """Group lines into ~size-char chunks, breaking after sentence ends when possible."""
    chunks, buf, page0 = [], [], None
    for page, line in lines:
        if page0 is None:
            page0 = page
        buf.append(line)
        text = _join(buf)
        if len(text) >= size and re.search(r"[.:؛!؟]$", line.strip()) or len(text) >= size * 1.6:
            chunks.append((page0, text))
            buf, page0 = [], None
    if buf:
        tail = _join(buf)
        if chunks and len(tail) < size * 0.3:
            chunks[-1] = (chunks[-1][0], chunks[-1][1] + " " + tail)
        else:
            chunks.append((page0, tail))
    return chunks


def build() -> None:
    pdf = config.RAW_DIR / "bayyinat" / "bayyinat.pdf"
    doc = pymupdf.open(pdf)
    pages = read_pages(doc)
    titles = parse_toc(pages)
    questions = split_questions(pages)
    if len(questions) != EXPECTED_QUESTIONS:
        raise RuntimeError(f"expected {EXPECTED_QUESTIONS} questions, found {len(questions)}")
    missing_titles = [q.n for q in questions if q.n not in titles]
    for i, q in enumerate(questions):
        _trim_next_title(q, questions[i + 1] if i + 1 < len(questions) else None)
        q.title = _clean_title(titles.get(q.n) or _join(q.question)[:120])

    filler = QuranFiller(VerbatimStore())
    records = []
    for q in questions:
        url = f"{PDF_URL}#page={q.page}"
        question_text, r1 = filler.fill(_join(q.question))
        summary, r2 = filler.fill(_join(q.summary))
        gist, r3 = filler.fill(_join(q.gist))
        similar = re.sub(f"[{QURAN_GAP}﴿﴾]", " ", _join(q.similar))
        parts = [f"السؤال: {q.title}", question_text]
        if similar:
            parts.append(f"عبارات مشابهة: {similar}")
        if gist:
            parts.append(f"مضمون السؤال: {gist}")
        parts.append(f"مختصر الإجابة: {summary}")
        records.append({
            "id": f"QA:bayyinat:{q.n}",
            "type": "qa",
            "title": q.title,
            "text_ar": "\n".join(p for p in parts if p),
            "translations": {},
            "source": SOURCE,
            "ref": f"بينات، السؤال {q.n}",
            "grade": None,
            "source_url": url,
            "question_n": q.n,
            "part": 1,
            "keywords": q.keywords.strip(),
            "quran_refs": sorted(set(r1 + r2 + r3)),
        })
        for k, (page, chunk) in enumerate(_chunks(q.detail), start=2):
            text, refs = filler.fill(chunk)
            records.append({
                "id": f"QA:bayyinat:{q.n}:{k}",
                "type": "qa",
                "title": q.title,
                "text_ar": f"السؤال: {q.title}\nمن الجواب التفصيلي: {text}",
                "translations": {},
                "source": SOURCE,
                "ref": f"بينات، السؤال {q.n} (الجواب التفصيلي، الجزء {k - 1})",
                "grade": None,
                "source_url": f"{PDF_URL}#page={page}",
                "question_n": q.n,
                "parent_id": f"QA:bayyinat:{q.n}",
                "part": k,
                "quran_refs": sorted(set(refs)),
            })

    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out = config.PROCESSED_DIR / "bayyinat.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    empty = [q.n for q in questions if not q.summary]
    print(f"Bayyinat: {len(questions)} questions, {len(records)} records -> {out}")
    if missing_titles:
        print(f"  warning: no TOC title for questions {missing_titles}")
    if empty:
        print(f"  warning: no short answer (مختصر الإجابة) found for questions {empty}")


if __name__ == "__main__":
    build()
