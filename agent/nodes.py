"""The agent's stages. Each node takes the state and returns only the keys it changes.

Stage map (docs/DISCLOSURE.md numbering):
  1 analyze   — language, level of knowledge, tone, real question, Arabic query, misquotes
  2 route     — level A-D (LLM, with a deterministic Level-D hint)
  3 retrieve  — hybrid search via retrieval.retrieve(); abstain below the threshold
  4 generate  — draft with placeholders only, glossary terms, level-specific rules
  5 verify    — deterministic checks against the verbatim store (+ optional LLM judge),
                then placeholders are replaced with the exact text
  refer / abstain — fixed, reviewed templates (no improvisation)
"""
from __future__ import annotations

import logging
import re
from typing import NamedTuple

from agent import llm, rules, settings, templates
from agent.prompts import load
from agent.state import AgentState, Analysis, Citation, Draft, Judgement, Routing
from retrieval import get_retriever
from retrieval.contract import Evidence

log = logging.getLogger("mueen.agent")

ROLE_NAMES = {"seeker": "Seeker", "dai": "Da'i", "da'i": "Da'i", "user": "Seeker", "assistant": "Da'i"}
UNVERIFIED_MARK = {"ar": "[⚠ مرجع غير موثّق — راجعه]", "en": "[⚠ unverified reference — check]"}


# ----------------------------------------------------------------- helpers ---
def _conversation(messages: list[dict]) -> str:
    recent = messages[-settings.CONTEXT_MESSAGES:]
    return "\n".join(f"{ROLE_NAMES.get(str(m.get('role', 'seeker')).lower(), 'Seeker')}: {m.get('text', '')}"
                     for m in recent)


def _last_seeker_text(messages: list[dict]) -> str:
    for m in reversed(messages):
        if str(m.get("role", "seeker")).lower() in ("seeker", "user"):
            return m.get("text", "")
    return messages[-1].get("text", "") if messages else ""


def _detect_language(text: str) -> tuple[str, float] | None:
    """fastText language id from the knowledge layer; None if its model is not available."""
    try:
        from retrieval.langid import detect_language

        return detect_language(text)
    except Exception as exc:  # model not downloaded, fasttext missing, ...
        log.debug("language id unavailable: %s", exc)
        return None


def _verbatim(ref_id: str, lang: str) -> Evidence | None:
    try:
        return get_retriever().get_verbatim(ref_id, lang)
    except FileNotFoundError:
        return None


def _quotes_in(text: str):
    """Ayah-like quotations in `text` (needs the verbatim store); [] if unavailable."""
    try:
        from retrieval.ayah_match import find_quran_quotes

        return find_quran_quotes(text)
    except FileNotFoundError:
        return []


def _quran_refs_in(text: str) -> list[str]:
    try:
        from retrieval.verbatim import quran_refs_in

        return quran_refs_in(text)
    except FileNotFoundError:
        return []


def _glossary_terms(texts: list[str], lang: str, limit: int = 15) -> list[dict]:
    try:
        from retrieval.glossary import glossary_for

        return glossary_for(texts, lang, limit)
    except Exception as exc:
        log.debug("glossary unavailable: %s", exc)
        return []


def gl_id(term: dict) -> str:
    """Stable id for a glossary entry: GL:<Jamhara word id>, or GL:<Arabic term> for pack-only terms."""
    return f"GL:{term.get('jamhara_id') or term['ar']}"


# Some Jamhara definitions embed Quran verses in PDF glyph codes (Arabic presentation forms)
# that cannot be rendered or verified; cut them out so the model never copies them.
_GLYPHS = re.compile(r"[\uFB50-\uFDFF\uFE70-\uFEFF﴾﴿]+")


def _clean_definition(text: str) -> str:
    text = re.split(r"ومن شواهده|انظر\s*:", text or "")[0]
    return re.sub(r"\s+", " ", _GLYPHS.sub(" ", text)).strip(" .،")


def _glossary_block(terms: list[dict], lang: str) -> tuple[str, dict[str, dict]]:
    lines, ids = [], {}
    for t in terms:
        gid = gl_id(t)
        ids[gid] = t
        equivalent = t.get(lang) or t.get(f"jamhara_{lang}") or t.get("en") or t.get("jamhara_en") or ""
        if lang == "ar":
            note = t.get("usage_rule_ar") or _clean_definition(t.get("definition_ar", ""))
        else:
            note = t.get("definition_en") or t.get("usage_rule_ar") or ""
        rule = f" [usage rule: {t['usage_rule_ar']}]" if lang != "ar" and t.get("usage_rule_ar") else ""
        lines.append(f"- [{gid}] {t['ar']} → {equivalent} — {note}{rule}")
    return "\n".join(lines), ids


def _localize(table: dict[str, str], lang: str) -> str:
    text, exact = templates.pick(table, lang)
    if exact:
        return text
    try:  # rare language: translate the reviewed English template, meaning unchanged
        return llm.text("translate", [
            ("system", "Translate the user's text into the language with ISO code "
                       f"'{lang}'. Keep the meaning exactly; add nothing; output only the translation."),
            ("user", text),
        ]) or text
    except Exception as exc:
        log.warning("template translation failed (%s); using English", exc)
        return text


def _trace(state: AgentState, name: str) -> list[str]:
    return [*state.get("trace", []), name]


# -------------------------------------------------------------- 1 analyze ---
def analyze(state: AgentState) -> dict:
    messages = state["messages"]
    seeker_text = _last_seeker_text(messages)
    a: Analysis = llm.structured("analyze", Analysis, [
        ("system", load("analyze")),
        ("user", f"Conversation (latest message last):\n{_conversation(messages)}"),
    ])

    # Language: offline fastText on the seeker's recent words when confident, else the LLM's answer.
    seeker_recent = " ".join(m.get("text", "") for m in messages[-3:]
                             if str(m.get("role", "seeker")).lower() in ("seeker", "user")) or seeker_text
    detected = _detect_language(seeker_recent)
    language = detected[0] if detected and detected[1] >= 0.5 else (a.language or "en").lower()[:2]

    # Quotes of the Quran in the seeker's message; inexact ones are misquotes (challenge case 11).
    misquotes = [{"ref_id": m.ref_id, "quoted": m.quoted, "similarity": m.similarity, "is_exact": m.is_exact}
                 for m in _quotes_in(seeker_text)]

    hint = "D" if (rules.level_d_hint(seeker_text) or a.personal_case) else None
    # Approved glossary entries for the term the seeker asks about (if any).
    terms = _glossary_terms([a.asked_term], language, limit=3) if a.asked_term.strip() else []
    return {"analysis": a, "language": language, "misquotes": misquotes, "level_hint": hint, "terms": terms,
            "attempts": 0, "issues": [], "trace": _trace(state, "analyze")}


# ---------------------------------------------------------------- 2 route ---
def route(state: AgentState) -> dict:
    a = state["analysis"]
    seeker_text = _last_seeker_text(state["messages"])
    hint = state.get("level_hint")
    hint_line = ("Keyword hint: the message may be a personal-ruling request (possible level D)."
                 if hint == "D" else "Keyword hint: none.")
    r: Routing = llm.structured("route", Routing, [
        ("system", load("route")),
        ("user", f"Seeker's message:\n{seeker_text}\n\nCore question (analyzer): {a.core_question}\n"
                 f"Personal case (analyzer): {a.personal_case}\n{hint_line}"),
    ])
    # Two independent signals (keyword rule AND analyzer) agreeing on a personal case => D,
    # following the pack's rule to pick the more cautious level when in doubt.
    if r.level != "D" and a.personal_case and rules.level_d_hint(seeker_text):
        r = Routing(level="D", reason=r.reason + " (رُفع إلى D: سؤال عن حالة شخصية)")
    return {"routing": r, "refer_reason": "personal" if r.level == "D" else None,
            "trace": _trace(state, "route")}


# ------------------------------------------------------------- 3 retrieve ---
def retrieve(state: AgentState) -> dict:
    a, lang = state["analysis"], state["language"]
    seeker_text = _last_seeker_text(state["messages"])
    # Seeker's own words + an Arabic reformulation: Recall@6 93% -> 98% (HANDOFF §2).
    queries = [q for q in [seeker_text, a.arabic_query, a.core_question] if q and q.strip()]
    retriever = get_retriever()
    threshold = settings.ABSTAIN_THRESHOLD

    if a.asks_for_hadith:
        # Hadith requests are answered only from hadith evidence; never fall back to
        # Quran/Bayyinat for them (HANDOFF §5.7).
        found = retriever.retrieve(queries, lang, types=["hadith"], k=6)
        kept = [e for e in found if e.score >= threshold]
        best = max((e.score for e in found), default=0.0)
        if not kept:
            return {"evidence": [], "best_score": best, "abstain_reason": "hadith_not_found",
                    "status": "abstain", "trace": _trace(state, "retrieve:no_hadith")}
    else:
        found = retriever.retrieve(queries, lang, k=6)
        kept = [e for e in found if e.score >= threshold]
        best = max((e.score for e in found), default=0.0)

    # The correct verse for a misquote must be in the evidence, or the verifier would reject it (HANDOFF §5.2).
    for m in state.get("misquotes", []):
        e = _verbatim(m["ref_id"], lang)
        if e and all(x.id != e.id for x in kept):
            kept.insert(0, e.model_copy(update={"score": 1.0}))

    if not kept:
        if state.get("terms") and state["analysis"].asks_term_meaning:
            # A question about an approved term (Tawhid, Sharia, ...): the glossary from the
            # challenge pack / Jamhara is the approved source, so draft from it.
            return {"evidence": [], "best_score": best, "abstain_reason": None,
                    "trace": _trace(state, "retrieve:glossary_only")}
        if state["analysis"].asks_for_verse:
            # "Give me the exact verse about X" with no matching verse: abstain, never improvise.
            return {"evidence": [], "best_score": best, "abstain_reason": "verse_not_found",
                    "status": "abstain", "trace": _trace(state, "retrieve:no_verse")}
        if state["routing"].level == "C":
            # Disputed/sensitive topic with no evidence: refer to a specialist (pack, level C).
            return {"evidence": [], "best_score": best, "status": "refer", "refer_reason": "specialist",
                    "trace": _trace(state, "retrieve:specialist")}
        return {"evidence": [], "best_score": best, "abstain_reason": "low_confidence",
                "status": "abstain", "trace": _trace(state, "retrieve:low_confidence")}
    return {"evidence": kept, "best_score": best, "abstain_reason": None, "trace": _trace(state, "retrieve")}


# ------------------------------------------------------------- 4 generate ---
_LEVEL_RULES = {
    "A": "Level A (settled facts): answer directly and cite the source.",
    "B": "Level B (explanation / general doubt): explain from the evidence, show the reference, and avoid "
         "certainty where scholars may differ.",
    "C": "Level C (disputed or sensitive): give a restricted answer, say that scholars differ where relevant, "
         "no claims of consensus, and suggest consulting a specialist for detail.",
}
_STYLE = {
    "simpler": "Make it simpler and shorter, for someone with no background.",
    "deeper": "Go a little deeper, still within the evidence.",
    "shorter": "Make it noticeably shorter (2-4 sentences).",
}


def _evidence_block(evidence: list[Evidence]) -> tuple[str, list[str]]:
    docs, embedded = [], []
    for e in evidence:
        body = e.text_ar + (f"\n[translation] {e.translation}" if e.translation else "")
        docs.append(f'<doc id="{e.id}" type="{e.type}" source="{e.source}" ref="{e.ref}">\n{body}\n</doc>')
        if e.type == "qa":
            embedded += [r for r in _quran_refs_in(e.text_ar) if r not in embedded]
    return "\n".join(docs), embedded


def generate(state: AgentState) -> dict:
    a, lang, r = state["analysis"], state["language"], state["routing"]
    evidence = state["evidence"]
    docs, embedded = _evidence_block(evidence)
    terms = {gl_id(t): t for t in state.get("terms", [])}
    for t in _glossary_terms([_conversation(state["messages"]), *[e.text_ar for e in evidence]], lang):
        terms.setdefault(gl_id(t), t)
    glossary, glossary_ids = _glossary_block(list(terms.values()), lang)

    misquote_note = ""
    wrong = [m for m in state.get("misquotes", []) if not m["is_exact"]]
    if wrong:
        misquote_note = "\nThe seeker misquoted a verse: " + "; ".join(
            f'they wrote "{m["quoted"]}", the correct verse is [[{m["ref_id"]}]]' for m in wrong)
    retry_note = ""
    if state.get("issues"):
        retry_note = ("\nYour previous draft was rejected by the verifier. Fix these problems:\n- "
                      + "\n- ".join(state["issues"]))

    user = (
        f"Conversation (latest message last):\n{_conversation(state['messages'])}\n\n"
        f"Seeker profile: language={lang}, knowledge_level={a.knowledge_level}, tone={a.tone}, "
        f"background={a.background}\nReal question: {a.core_question}\n"
        f"{_LEVEL_RULES.get(r.level, _LEVEL_RULES['B'])}\n"
        f"{_STYLE.get(state.get('style') or '', '')}{misquote_note}\n\n"
        f"<evidence>\n{docs or 'none — answer only from the glossary entries below'}\n</evidence>\n\n"
        f"<allowed_quran_refs>{', '.join(embedded) or 'none'}</allowed_quran_refs>\n\n"
        f"<glossary>\n{glossary or 'none'}\n</glossary>{retry_note}"
    )
    d: Draft = llm.structured("generate", Draft, [
        ("system", load("generate").replace("{language}", lang)),
        ("user", user),
    ])
    return {"draft": d, "glossary": glossary_ids, "attempts": state.get("attempts", 0) + 1,
            "trace": _trace(state, "generate")}


# --------------------------------------------------------------- 5 verify ---
def _allowed_ids(evidence: list[Evidence]) -> set[str]:
    allowed = {e.id for e in evidence}
    for e in evidence:
        if e.type == "qa":
            allowed.update(_quran_refs_in(e.text_ar))  # verses quoted inside a cited Bayyinat passage
    return allowed


def _quote_to_placeholder(text: str, allowed: set[str], evidence_key: str = "") -> str:
    """Replace Quran text the model typed itself with a placeholder when that verse is in the
    evidence — as a retrieved id, or copied from a retrieved passage (Bayyinat quotes verses) —
    so the reply shows the store's exact text instead (deterministic repair)."""
    from retrieval.normalize_ar import norm as normalize

    for q in _quotes_in(rules.strip_placeholders(text)):
        copied = bool(evidence_key) and normalize(q.quoted) in evidence_key
        if (rules.is_covered(q.ref_id, allowed) or copied) and q.quoted in text:
            span = re.compile(r"[«\"“(]?\s*" + re.escape(q.quoted) + r"\s*[»\"”)]?")
            text = span.sub(f"[[{q.ref_id}]]", text, count=1)
    return text


def repair_draft(d: Draft, evidence: list[Evidence]) -> Draft:
    from retrieval.normalize_ar import norm as normalize

    allowed = _allowed_ids(evidence)
    key = normalize(" ".join(e.text_ar for e in evidence))
    return d.model_copy(update={"reply": _quote_to_placeholder(d.reply, allowed, key),
                                "reply_ar": _quote_to_placeholder(d.reply_ar, allowed, key)})


def check_draft(d: Draft, evidence: list[Evidence], lang: str, level: str,
                glossary_ids: set[str] | None = None) -> list[str]:
    """Deterministic verification. Returns the list of problems (empty = passes)."""
    issues: list[str] = []
    allowed = _allowed_ids(evidence)
    glossary_ids = glossary_ids or set()
    for rid in dict.fromkeys(rules.placeholders(d.reply) + rules.placeholders(d.reply_ar)):
        if not rules.is_covered(rid, allowed):
            issues.append(f"placeholder [[{rid}]] is not in the retrieved evidence")
        elif _verbatim(rid, lang) is None:
            issues.append(f"placeholder [[{rid}]] does not exist in the verbatim store")
    ev_ids = {e.id for e in evidence}
    for cid in d.cited_ids:
        if cid not in ev_ids and cid not in glossary_ids and not rules.is_covered(cid, allowed):
            issues.append(f"cited id {cid} is not in the evidence")
    if not d.cited_ids and not rules.placeholders(d.reply):
        issues.append("the reply cites no evidence; cite the evidence ids you used")
    for field, txt in (("reply", d.reply), ("reply_ar", d.reply_ar)):
        if rules.QUOTE_MARKS.search(rules.strip_placeholders(txt)):
            issues.append(f"{field} uses the Quran brackets ﴿﴾ outside a placeholder; use placeholders only")
    for q in _quotes_in(rules.strip_placeholders(d.reply)):
        issues.append(f"the reply contains Quran-like text ({q.ref_id}) outside a placeholder; "
                      f"use [[{q.ref_id}]] instead")
    if level == "C":
        for p in rules.certainty_claims(d.reply) + rules.certainty_claims(d.reply_ar):
            issues.append(f'level C: remove the claim of certainty/consensus "{p}"')
    return issues


class Judged(NamedTuple):
    blocking: list[str]   # contradictions: retry, then "unverified"
    advisory: list[str]   # unsupported details: shown to the da'i


def _judge(d: Draft, evidence: list[Evidence]) -> Judged | None:
    """Independent LLM check of every religious claim. None = the judge could not run
    (fail-open: deterministic checks still apply, and the da'i is told)."""
    docs, _ = _evidence_block(evidence)
    try:
        j: Judgement = llm.structured("judge", Judgement, [
            ("system", load("judge")),
            ("user", f"<evidence>\n{docs}\n</evidence>\n\n<draft>\n{d.reply}\n</draft>"),
        ])
    except Exception as exc:
        log.warning("LLM judge failed (%s); deterministic checks only", exc)
        return None
    if j.grounded:
        return Judged([], [])
    issues = j.issues or ["the judge found claims not supported by the evidence"]
    # Contradicting the evidence blocks the draft (retry, then "unverified"); claims that are merely
    # not in the evidence are shown to the da'i as review points (human in the loop) — a strict
    # judge flags some detail in most drafts, and blocking those would hide useful drafts.
    return Judged([f"contradicts the evidence: {i}" for i in issues], []) if j.contradicts \
        else Judged([], [f"not in the evidence: {i}" for i in issues])


def _render(text: str, lang: str, evidence: dict[str, Evidence]) -> str:
    def sub(m):
        rid = m.group(1)
        e = _verbatim(rid, lang) if rid.startswith(("Q:", "H:")) else None
        return rules.render(e, lang) if e else UNVERIFIED_MARK.get(lang, UNVERIFIED_MARK["en"])
    return rules.tidy(rules.PLACEHOLDER.sub(sub, text))


def _citations(d: Draft, evidence: list[Evidence], lang: str,
               glossary: dict[str, dict] | None = None) -> list[Citation]:
    by_id = {e.id: e for e in evidence}
    out: list[Citation] = []
    for cid in dict.fromkeys([*rules.placeholders(d.reply), *d.cited_ids]):
        if glossary and cid in glossary:
            t = glossary[cid]
            out.append(Citation(id=cid, type="glossary", source=t.get("source", "Glossary"), ref=t["ar"],
                                source_url=t.get("source_url", "")))
            continue
        e = by_id.get(cid) or (_verbatim(cid, lang) if cid.startswith(("Q:", "H:")) else None)
        if e and all(c.id != e.id for c in out):
            out.append(Citation(id=e.id, type=e.type, source=e.source, ref=e.ref,
                                source_url=e.source_url, grade=e.grade))
    return out


def verify(state: AgentState) -> dict:
    evidence, lang = state["evidence"], state["language"]
    d = repair_draft(state["draft"], evidence)
    level = state["routing"].level
    glossary = state.get("glossary", {})
    issues = check_draft(d, evidence, lang, level, set(glossary))
    judge_down, advisory = False, []
    if not issues and settings.VERIFY_LLM_JUDGE:
        judged = _judge(d, evidence)
        judge_down = judged is None
        if judged:
            issues, advisory = judged.blocking, judged.advisory

    attempts = state.get("attempts", 1)
    if issues and attempts < settings.MAX_DRAFT_ATTEMPTS:
        return {"issues": issues, "verdict": "retry", "retry_issues": [*state.get("retry_issues", []), *issues],
                "trace": _trace(state, "verify:retry")}

    by_id = {e.id: e for e in evidence}
    note = d.note_for_dai
    if issues:  # second failure: shown to the da'i, clearly marked (DECISIONS: not hidden)
        note = "⚠ لم تجتز المسودة التحقق الآلي — راجع المراجع قبل الإرسال. " + note
    elif judge_down:
        note = "ℹ️ تعذّر التحقق الثاني (المحكّم الآلي)؛ اجتازت المسودة الفحص الحتمي فقط. " + note
    elif advisory:
        note = (f"🔎 المحكّم الآلي وجد {len(advisory)} نقطة غير موجودة في الأدلة — راجعها في issues قبل الإرسال. "
                + note)
    return {
        "verdict": "fail" if issues else "pass",
        "status": "unverified" if issues else "ok",
        "issues": [*issues, *advisory],
        "final_reply": _render(d.reply, lang, by_id),
        "final_reply_ar": _render(d.reply_ar, "ar", by_id),
        "note_for_dai": note,
        "citations": _citations(d, evidence, lang, glossary),
        "trace": _trace(state, "verify:judge_unavailable" if judge_down else "verify"),
    }


# ------------------------------------------------------- refer / abstain ---
def refer(state: AgentState) -> dict:
    lang, r = state["language"], state["routing"]
    if state.get("refer_reason") == "specialist":
        table = templates.REFER_SPECIALIST
        note = (f"🟠 مستوى C بلا أدلة كافية في المصادر المعتمدة (أعلى درجة {state.get('best_score', 0):.2f}): "
                f"أُحيل السائل لمتخصص. {r.reason}")
    else:
        table = templates.REFER
        note = f"🔴 مستوى D (حالة شخصية/فتوى): لا يُعطى حكم. {r.reason} — أُحيل السائل لعالِم مؤهَّل."
    return {
        "status": "refer",
        "final_reply": _localize(table, lang),
        "final_reply_ar": table["ar"],
        "note_for_dai": note,
        "citations": [], "evidence": [], "issues": [],
        "trace": _trace(state, "refer"),
    }


def abstain(state: AgentState) -> dict:
    lang = state["language"]
    hadith = state.get("abstain_reason") == "hadith_not_found"
    table = templates.ABSTAIN_HADITH if hadith else templates.ABSTAIN
    why = ("طُلب حديث ولا يوجد حديث صحيح مطابق في المصادر المعتمدة" if hadith
           else f"أعلى درجة ثقة {state.get('best_score', 0):.2f} أقل من حد الامتناع {settings.ABSTAIN_THRESHOLD:.2f}")
    return {
        "status": "abstain",
        "final_reply": _localize(table, lang),
        "final_reply_ar": table["ar"],
        "note_for_dai": f"⚪ امتناع: {why}. يمكنك الإجابة بنفسك أو طلب توضيح من السائل.",
        "citations": [], "issues": [],
        "trace": _trace(state, "abstain"),
    }
