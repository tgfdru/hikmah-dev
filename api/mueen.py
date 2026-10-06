"""POST /mueen/draft — the Sheykak app's Mu'een endpoint.

The app (React Native, `src/features/mueen` in Sheykak-Mueen) talks to one interface,
`MueenService.generateDraft(MueenDraftRequest) -> MueenDraft`: a draft made of paragraphs,
each followed by the sources it rests on. This module adapts the agent to that shape:

* response = the app's v2 `MueenDraft`: `status` ok / no_sources, source kinds quran ·
  hadith (HadeethEnc) · book (Shamela) · dawah (Bayyinat) · other (glossary).
* request  -> agent conversation: the question card and the chat's text messages (asker =
  seeker, scholar = da'i); a "selected" scope answers the picked asker messages.
* draft    -> paragraphs: the verified draft is split at blank lines. A paragraph's Quran and
  hadith come from its own [[Q:..]]/[[H:..]] placeholders; the exact text goes into the
  source's `quote` (from the verbatim store), and the placeholder in the paragraph becomes a
  short reference. Explanatory sources the model cited (Bayyinat, Shamela, glossary) are
  attached to the paragraph closest in meaning (BGE-M3), since the model cites them per
  draft, not per paragraph.
* audience="scholar": the reader is a scholar, so level D (personal case) is drafted from
  the general evidence with a note, instead of the seeker-facing referral (agent/graph.py).

When the agent abstains or refers there is nothing to send: `paragraphs` is empty and
`notice` tells the scholar why (Arabic).
"""
from __future__ import annotations

import logging
import re
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from agent import rules
from agent.nodes import _verbatim
from retrieval.contract import Evidence

log = logging.getLogger("mueen.api")

MAX_MESSAGES = 50
MAX_TEXT = 4000

# The app's v2 source types (Sheykak-Mobile, src/features/mueen/types.ts).
SourceKind = Literal["quran", "hadith", "tafsir", "aqeedah", "dawah", "book", "other"]
Grade = Literal["sahih", "hasan", "daif"]


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# ------------------------------------------------------------------ request ---
class MueenQuestion(_Camel):
    title: str = Field(max_length=MAX_TEXT)
    description: str | None = Field(default=None, max_length=MAX_TEXT)


class MueenInputMessage(_Camel):
    id: str = Field(max_length=128)
    text: str = Field(max_length=MAX_TEXT)
    from_asker: bool


class MueenScope(_Camel):
    kind: Literal["all", "selected"]
    message_ids: list[str] = Field(default_factory=list, max_length=MAX_MESSAGES)


class MueenDraftRequest(_Camel):
    question_id: str = Field(min_length=1, max_length=128)
    question: MueenQuestion | None = None
    messages: list[MueenInputMessage] = Field(default_factory=list, max_length=200)
    scope: MueenScope


# ----------------------------------------------------------------- response ---
class MueenSource(_Camel):
    id: str
    kind: SourceKind
    collection: str
    reference: str | None = None
    quote: str | None = None
    translation: str | None = None   # approved translation of the quote (non-Arabic replies)
    attribution: str | None = None
    grade: Grade | None = None
    url: str | None = None


class MueenParagraph(_Camel):
    id: str
    text: str
    sources: list[MueenSource]


class MueenDraft(_Camel):
    id: str
    question_id: str
    scope: MueenScope
    paragraphs: list[MueenParagraph]
    text_message_count: int
    # The app's v2 status: "no_sources" = not enough approved references, so no draft.
    status: Literal["ok", "no_sources"]
    # Not in the app's MueenDraft type (extra fields are ignored until it uses them):
    outcome: Literal["ok", "unverified", "abstain", "refer"] = Field(
        description="The agent's result: unverified = shown but failed the checks; refer = out of scope")
    level: Literal["A", "B", "C", "D"] | None = None
    language: str | None = None
    notice: str = Field(description="Arabic note for the scholar: approach, warnings, or why there is no draft")
    review_points: list[str] = Field(default_factory=list, description="Claims the checkers asked to review")
    latency_ms: int = 0


class NoAskerText(ValueError):
    """The request has no asker text to answer."""


# ------------------------------------------------------- request -> agent ---
QUESTION_ITEM_ID = "__question__"  # the app sends the question card as a message with this id too


def to_conversation(req: MueenDraftRequest) -> tuple[list[dict], int]:
    """Agent messages (oldest first, the text to answer last) and the app's
    `textMessageCount` (computed like the app's mock service)."""
    msgs = [m for m in req.messages if m.text.strip()]
    card_msg = next((m for m in msgs if m.id == QUESTION_ITEM_ID), None)
    msgs = [m for m in msgs if m.id != QUESTION_ITEM_ID]
    if card_msg:
        card = card_msg.text.strip()
    elif req.question:
        card = "\n".join(x for x in (req.question.title.strip(), (req.question.description or "").strip()) if x)
    else:
        card = ""

    if req.scope.kind == "selected":
        picked = set(req.scope.message_ids)
        answer_card = QUESTION_ITEM_ID in picked
        answered = [m for m in msgs if m.id in picked and m.from_asker]
        context = [m for m in msgs if m.id not in picked]  # earlier messages stay as context
        count = len(req.scope.message_ids)
    else:
        # Everything the asker wrote since the scholar last replied is answered together;
        # before the scholar's first reply that includes the question card itself.
        last_scholar = max((i for i, m in enumerate(msgs) if not m.from_asker), default=-1)
        answer_card = last_scholar == -1
        answered = [m for m in msgs[last_scholar + 1:] if m.from_asker]
        context = msgs[: last_scholar + 1]
        count = sum(1 for m in req.messages if m.from_asker and m.text.strip())

    out: list[dict] = []
    if card and not answer_card:
        out.append({"role": "seeker", "text": card[:MAX_TEXT]})
    out += [{"role": "seeker" if m.from_asker else "dai", "text": m.text.strip()[:MAX_TEXT]}
            for m in context[-(MAX_MESSAGES - 2):]]
    to_answer = ([card] if card and answer_card else []) + [m.text.strip() for m in answered]
    if to_answer:
        out.append({"role": "seeker", "text": "\n\n".join(to_answer)[:MAX_TEXT]})
    if not any(m["role"] == "seeker" for m in out):
        raise NoAskerText("no text from the asker to answer")
    return out, count


# ------------------------------------------------------- agent -> app draft ---
def _grade(text: str | None) -> Grade | None:
    t = text or ""
    if "ضعيف" in t or "weak" in t.lower():
        return "daif"
    if "صحيح" in t or "صحح" in t or "authentic" in t.lower() or "sahih" in t.lower():
        return "sahih"
    if "حسن" in t or "hasan" in t.lower() or "good" in t.lower():
        return "hasan"
    return None


def _first_line(text: str, limit: int = 140) -> str:
    line = (text or "").strip().split("\n", 1)[0]
    line = re.sub(r"^السؤال\s*:\s*", "", line)
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"


_KFC = "نص القرآن: مجمع الملك فهد"


def _quran_source(e: Evidence, tr: str | None) -> MueenSource:
    """The app's Quran card: collection "سورة مريم", pill "مريم 30", attribution
    "سورة مريم · الآية 30 · نص القرآن: مجمع الملك فهد"."""
    surah = (e.ref or "").split(":", 1)[0].strip()
    m = re.fullmatch(r"Q:\d+:(\d+)(?:-(\d+))?", e.id)
    a, b = (int(m.group(1)), int(m.group(2) or m.group(1))) if m else (0, 0)
    span = f"{a}" if a == b else f"{a}–{b}"
    label = f"الآية {a}" if a == b else (f"الآيتان {span}" if b - a == 1 else f"الآيات {span}")
    return MueenSource(id=e.id, kind="quran", collection=f"سورة {surah}", reference=f"{surah} {span}",
                       quote=f"﴿{e.text_ar}﴾", translation=tr,
                       attribution=f"سورة {surah} · {label} · {_KFC}", url=e.source_url)


def evidence_source(e: Evidence, lang: str) -> MueenSource:
    """One citation chip from a piece of evidence (exact text from the store, never the model)."""
    tr = e.translation if lang != "ar" else None
    if e.type == "quran":
        return _quran_source(e, tr)
    if e.type == "hadith":  # HadeethEnc (or Dorar when enabled)
        return MueenSource(id=e.id, kind="hadith", collection=e.source,
                           quote=e.text_ar if "«" in e.text_ar else f"«{e.text_ar}»", translation=tr,
                           attribution=e.ref or None, grade=_grade(e.grade), url=e.source_url)
    if e.type in ("dawah", "book") and e.id.startswith(("SH:", "BK:shamela")):
        book = re.sub(r"\s*\(المكتبة الشاملة\)\s*$", "", e.source or "")
        return MueenSource(id=e.id, kind="book", collection="المكتبة الشاملة",
                           quote=book, attribution=e.ref, url=e.source_url)
    # Bayyinat (a Q&A on a doubt about Islam) and other explanatory sources: a da'wah topic card.
    return MueenSource(id=e.id, kind="dawah", collection=e.source,
                       quote=_first_line(e.text_ar) or None, attribution=e.ref, url=e.source_url or None)


def glossary_source(gid: str, term: dict, lang: str) -> MueenSource:
    equivalent = term.get(lang) or term.get(f"jamhara_{lang}") or term.get("en") or term.get("jamhara_en") or ""
    quote = term["ar"] + (f" — {equivalent}" if equivalent and lang != "ar" else "")
    return MueenSource(id=gid, kind="other", collection=term.get("source") or "قاموس المصطلحات",
                       reference=term["ar"], quote=quote, url=term.get("source_url") or None)


def _inline_label(e: Evidence, lang: str) -> str:
    """What replaces a placeholder inside the paragraph text; the exact text is in the chip."""
    if e.type == "quran":
        return f"({e.ref})" if lang == "ar" else f"({rules._quran_label(e.id, lang)})"
    return {"ar": "(حديث)", "ur": "(حدیث)"}.get(lang, "(hadith)")


def _split_paragraphs(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    return parts or ([text.strip()] if (text or "").strip() else [])


def _assign_by_meaning(paragraphs: list[str], items: list[tuple[str, str]]) -> dict[str, int]:
    """item id -> index of the paragraph closest in meaning (multilingual BGE-M3)."""
    if not items:
        return {}
    if len(paragraphs) == 1:
        return {i: 0 for i, _ in items}
    try:
        from retrieval.models import embed

        pv = embed([rules.strip_placeholders(p) for p in paragraphs])
        iv = embed([t[:1500] for _, t in items])
        best = (iv @ pv.T).argmax(axis=1)
        return {iid: int(b) for (iid, _), b in zip(items, best)}
    except Exception as exc:  # no model available (mock retriever): keep them with the first paragraph
        log.debug("source placement fell back to paragraph 1: %s", exc)
        return {i: 0 for i, _ in items}


def build_paragraphs(out: dict, lang: str) -> list[MueenParagraph]:
    """Paragraphs with their sources from the agent's result (status ok / unverified)."""
    evidence: dict[str, Evidence] = {e.id: e for e in out.get("evidence", [])}
    glossary: dict[str, dict] = out.get("glossary_used", {})
    texts = _split_paragraphs(out.get("draft_reply", ""))
    paragraphs: list[tuple[str, list[MueenSource]]] = []
    placed: set[str] = set()

    for text in texts:
        sources: list[MueenSource] = []

        def sub(m: re.Match) -> str:
            rid = m.group(1)
            e = _verbatim(rid, lang)
            if not e:
                return "[⚠]"
            if rid not in placed:
                sources.append(evidence_source(e, lang))
                placed.add(rid)
            return _inline_label(e, lang)

        clean = rules.tidy(rules.PLACEHOLDER.sub(sub, text))
        paragraphs.append((clean, sources))

    # Explanatory sources and glossary terms the model cited: next to the closest paragraph.
    rest: list[tuple[str, str]] = []
    chips: dict[str, MueenSource] = {}
    for cid in dict.fromkeys(out.get("draft_cited_ids", [])):
        if cid in placed:
            continue
        if cid in glossary:
            t = glossary[cid]
            chips[cid] = glossary_source(cid, t, lang)
            rest.append((cid, f"{t['ar']} {t.get(lang) or t.get('en') or ''}"))
        elif cid in evidence:
            e = evidence[cid]
            chips[cid] = evidence_source(e, lang)
            rest.append((cid, e.text_ar))
        elif cid.startswith(("Q:", "H:")) and (e := _verbatim(cid, lang)):
            chips[cid] = evidence_source(e, lang)
            rest.append((cid, e.text_ar))
    where = _assign_by_meaning([t for t, _ in paragraphs], rest)
    for cid, idx in where.items():
        paragraphs[idx][1].append(chips[cid])

    return [MueenParagraph(id=f"p{i + 1}", text=t, sources=s) for i, (t, s) in enumerate(paragraphs) if t]


def to_app_draft(req: MueenDraftRequest, out: dict, text_count: int) -> MueenDraft:
    lang = (out.get("analysis") or {}).get("language") or "ar"
    outcome = out.get("status", "unverified")
    paragraphs = build_paragraphs(out, lang) if outcome in ("ok", "unverified") else []
    notice = out.get("note_for_dai", "")
    if outcome in ("abstain", "refer"):
        notice = ("لم يُعدّ معين مسودة لهذا السؤال. " + notice).strip()
    return MueenDraft(
        id=f"mueen_{uuid.uuid4().hex[:12]}", question_id=req.question_id, scope=req.scope,
        paragraphs=paragraphs, text_message_count=text_count,
        status="ok" if paragraphs else "no_sources", outcome=outcome, level=out.get("level"),
        language=lang, notice=notice, review_points=list(out.get("issues", [])),
        latency_ms=int(out.get("latency_ms", 0)),
    )
