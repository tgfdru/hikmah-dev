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


def _glossary(texts: list[str], lang: str) -> str:
    try:
        from retrieval.glossary import format_for_prompt, glossary_for

        return format_for_prompt(glossary_for(texts, lang), lang)
    except Exception as exc:
        log.debug("glossary unavailable: %s", exc)
        return ""


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
    return {"analysis": a, "language": language, "misquotes": misquotes, "level_hint": hint,
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
    return {"routing": r, "trace": _trace(state, "route")}


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
                    "status": "abstain", "trace": _trace(state, "retrieve")}
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
        return {"evidence": [], "best_score": best, "abstain_reason": "low_confidence",
                "status": "abstain", "trace": _trace(state, "retrieve")}
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
    glossary = _glossary([_conversation(state["messages"]), *[e.text_ar for e in evidence]], lang)

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
        f"<evidence>\n{docs}\n</evidence>\n\n"
        f"<allowed_quran_refs>{', '.join(embedded) or 'none'}</allowed_quran_refs>\n\n"
        f"<glossary>\n{glossary or 'none'}\n</glossary>{retry_note}"
    )
    d: Draft = llm.structured("generate", Draft, [
        ("system", load("generate").replace("{language}", lang)),
        ("user", user),
    ])
    return {"draft": d, "attempts": state.get("attempts", 0) + 1, "trace": _trace(state, "generate")}


# --------------------------------------------------------------- 5 verify ---
def _allowed_ids(evidence: list[Evidence]) -> set[str]:
    allowed = {e.id for e in evidence}
    for e in evidence:
        if e.type == "qa":
            allowed.update(_quran_refs_in(e.text_ar))  # verses quoted inside a cited Bayyinat passage
    return allowed


def check_draft(d: Draft, evidence: list[Evidence], lang: str, level: str) -> list[str]:
    """Deterministic verification. Returns the list of problems (empty = passes)."""
    issues: list[str] = []
    allowed = _allowed_ids(evidence)
    for rid in dict.fromkeys(rules.placeholders(d.reply) + rules.placeholders(d.reply_ar)):
        if not rules.is_covered(rid, allowed):
            issues.append(f"placeholder [[{rid}]] is not in the retrieved evidence")
        elif _verbatim(rid, lang) is None:
            issues.append(f"placeholder [[{rid}]] does not exist in the verbatim store")
    ev_ids = {e.id for e in evidence}
    for cid in d.cited_ids:
        if cid not in ev_ids and not rules.is_covered(cid, allowed):
            issues.append(f"cited id {cid} is not in the evidence")
    if not d.cited_ids and not rules.placeholders(d.reply):
        issues.append("the reply cites no evidence; cite the evidence ids you used")
    for field, txt in (("reply", d.reply), ("reply_ar", d.reply_ar)):
        if rules.QUOTE_MARKS.search(rules.strip_placeholders(txt)):
            issues.append(f"{field} uses ﴿﴾ or «» outside a placeholder; use placeholders only")
    for q in _quotes_in(rules.strip_placeholders(d.reply)):
        issues.append(f"the reply contains Quran-like text ({q.ref_id}) outside a placeholder; "
                      f"use [[{q.ref_id}]] instead")
    if level == "C":
        for p in rules.certainty_claims(d.reply) + rules.certainty_claims(d.reply_ar):
            issues.append(f'level C: remove the claim of certainty/consensus "{p}"')
    return issues


def _judge(d: Draft, evidence: list[Evidence]) -> list[str]:
    docs, _ = _evidence_block(evidence)
    try:
        j: Judgement = llm.structured("judge", Judgement, [
            ("system", load("judge")),
            ("user", f"<evidence>\n{docs}\n</evidence>\n\n<draft>\n{d.reply}\n</draft>"),
        ])
    except Exception as exc:
        log.warning("LLM judge failed (%s); deterministic checks only", exc)
        return []
    return [] if j.grounded else [f"unsupported claim: {i}" for i in j.issues] or ["judge: not grounded"]


def _render(text: str, lang: str, evidence: dict[str, Evidence]) -> str:
    def sub(m):
        rid = m.group(1)
        e = _verbatim(rid, lang) if rid.startswith(("Q:", "H:")) else None
        return rules.render(e, lang) if e else UNVERIFIED_MARK.get(lang, UNVERIFIED_MARK["en"])
    return rules.tidy(rules.PLACEHOLDER.sub(sub, text))


def _citations(d: Draft, evidence: list[Evidence], lang: str) -> list[Citation]:
    by_id = {e.id: e for e in evidence}
    out: list[Citation] = []
    for cid in dict.fromkeys([*rules.placeholders(d.reply), *d.cited_ids]):
        e = by_id.get(cid) or (_verbatim(cid, lang) if cid.startswith(("Q:", "H:")) else None)
        if e and all(c.id != e.id for c in out):
            out.append(Citation(id=e.id, type=e.type, source=e.source, ref=e.ref,
                                source_url=e.source_url, grade=e.grade))
    return out


def verify(state: AgentState) -> dict:
    d, evidence, lang = state["draft"], state["evidence"], state["language"]
    level = state["routing"].level
    issues = check_draft(d, evidence, lang, level)
    if not issues and settings.VERIFY_LLM_JUDGE:
        issues = _judge(d, evidence)

    attempts = state.get("attempts", 1)
    if issues and attempts < settings.MAX_DRAFT_ATTEMPTS:
        return {"issues": issues, "verdict": "retry", "trace": _trace(state, "verify:retry")}

    by_id = {e.id: e for e in evidence}
    note = d.note_for_dai
    if issues:  # second failure: shown to the da'i, clearly marked (DECISIONS: not hidden)
        note = "⚠ لم تجتز المسودة التحقق الآلي — راجع المراجع قبل الإرسال. " + note
    return {
        "verdict": "fail" if issues else "pass",
        "status": "unverified" if issues else "ok",
        "issues": issues,
        "final_reply": _render(d.reply, lang, by_id),
        "final_reply_ar": _render(d.reply_ar, "ar", by_id),
        "note_for_dai": note,
        "citations": _citations(d, evidence, lang),
        "trace": _trace(state, "verify"),
    }


# ------------------------------------------------------- refer / abstain ---
def refer(state: AgentState) -> dict:
    lang, r = state["language"], state["routing"]
    return {
        "status": "refer",
        "final_reply": _localize(templates.REFER, lang),
        "final_reply_ar": templates.REFER["ar"],
        "note_for_dai": f"🔴 مستوى D (حالة شخصية/فتوى): لا يُعطى حكم. {r.reason} — أُحيل السائل لعالِم مؤهَّل.",
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
