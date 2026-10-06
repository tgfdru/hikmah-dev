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

import json
import logging
import re
from typing import NamedTuple

from agent import llm, rules, settings, templates
from agent.language import detect_confident
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
    # The reply language is decided before the graph (agent.language.resolve_response_language: the
    # message being answered, with fallbacks). The old guess below is kept only for direct graph use.
    language = state.get("language") or (
        detected[0] if detected and detected[1] >= 0.5 else (a.language or "en").lower()[:2])
    # The resolver had no reliable signal (no confident message, no fallback given): the analyzer,
    # which read the message being answered, decides.
    decision = dict(state.get("language_decision") or {})
    if decision.get("source") in ("default", "target_message_weak") and a.language:
        language = a.language.lower()[:2]
        decision.update(language=language, source="analyzer")

    # Quotes of the Quran in the seeker's message; inexact ones are misquotes (challenge case 11).
    misquotes = [{"ref_id": m.ref_id, "quoted": m.quoted, "similarity": m.similarity, "is_exact": m.is_exact}
                 for m in _quotes_in(seeker_text)]

    hint = "D" if (rules.level_d_hint(seeker_text) or a.personal_case) else None
    # Approved glossary entries for the term the seeker asks about (if any).
    terms = _glossary_terms([a.asked_term], language, limit=3) if a.asked_term.strip() else []
    return {"analysis": a, "language": language, "language_decision": decision, "misquotes": misquotes, "level_hint": hint, "terms": terms,
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
    if a.judges_people and r.level != "D":
        # The pack excludes judging persons and groups: no generated verdict, fixed referral.
        r = Routing(level="C", reason=r.reason + " (حكم على أشخاص/جماعات: خارج النطاق، يُحال للعلماء)")
        return {"routing": r, "refer_reason": "judgement", "status": "refer",
                "trace": _trace(state, "route:judgement")}
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
    # Reached only when the reader is a scholar (audience="scholar"); a seeker gets the fixed referral.
    "D": "Level D (a personal case; a qualified scholar reads this draft and decides): present only the general "
         "evidence and principles found in the evidence. Do NOT give a ruling on this person's specific case and "
         "do not tell them what they must do. End with one sentence saying that the ruling depends on the details "
         "of their situation.",
}
_STYLE = {
    "simpler": "Make it simpler and shorter, for someone with no background.",
    "deeper": "Go a little deeper, still within the evidence.",
    "shorter": "Make it noticeably shorter (2-4 sentences).",
}


# Explanatory sources (not scripture): explained in the model's words, never quoted as scripture;
# verses they quote as "[البقرة: 144]" may be cited with placeholders.
EXPLANATION_TYPES = {"qa", "tafsir", "dawah", "book"}


def _evidence_block(evidence: list[Evidence]) -> tuple[str, list[str]]:
    docs, embedded = [], []
    for e in evidence:
        body = e.text_ar + (f"\n[translation] {e.translation}" if e.translation else "")
        docs.append(f'<doc id="{e.id}" type="{e.type}" source="{e.source}" ref="{e.ref}">\n{body}\n</doc>')
        if e.type in EXPLANATION_TYPES:
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
        f"Message you are answering (the seeker's own words):\n{_last_seeker_text(state['messages'])}\n\n"
        f"Write the reply in: {lang}\n"
        f"Seeker profile (for HOW you write, never for WHAT is true): knowledge_level={a.knowledge_level}, "
        f"tone={a.tone}, background={a.background}\nReal question: {a.core_question}\n"
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
        if e.type in EXPLANATION_TYPES:
            allowed.update(_quran_refs_in(e.text_ar))  # verses quoted inside a cited Bayyinat/Shamela/book passage
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


_GL_INLINE = re.compile(r"\[{1,2}\s*(GL:[^\]\s]+)\s*\]{1,2}")


def inline_ids_to_text(d: Draft, lang: str, glossary: dict[str, dict]) -> Draft:
    """The model often writes ids into the text ("[[GL:5744]]", "([SH:69:7])"). A glossary id
    becomes the approved term in the reply's language (and is cited); other stray ids are
    removed from the text by rules.tidy at render time. Deterministic, no retry needed."""
    cited = list(d.cited_ids)

    def fix(text: str, text_lang: str) -> str:
        def sub(m):
            gid = m.group(1)
            t = glossary.get(gid)
            if not t:
                return ""
            if gid not in cited:
                cited.append(gid)
            return t["ar"] if text_lang == "ar" else (t.get(text_lang) or t.get("en") or t["ar"])
        return _GL_INLINE.sub(sub, text or "")
    reply, reply_ar = fix(d.reply, lang), fix(d.reply_ar, "ar")
    return d.model_copy(update={"reply": reply, "reply_ar": reply_ar, "cited_ids": cited})


def _glossary_latin(glossary_ids: set[str] | None) -> set[str]:
    """Latin words of the approved glossary equivalents in use (e.g. "Tawhid"), allowed in
    Arabic-script replies."""
    words: set[str] = set()
    for gid in glossary_ids or set():
        words.update(re.findall(r"[A-Za-z][A-Za-z'’-]+", gid))
    try:
        from retrieval.glossary import load_glossary  # noqa: WPS433
        for t in load_glossary():
            if gl_id(t) in (glossary_ids or set()):
                words.update(re.findall(r"[A-Za-z][A-Za-z'’-]+", json.dumps(t, ensure_ascii=False)))
    except Exception:  # noqa: BLE001 — the glossary is a convenience here, never a failure
        pass
    return words


def _strip_rendered(text: str) -> str:
    """Draft text without placeholders or quoted scripture, for language detection."""
    return rules.QUOTE_MARKS.sub(" ", rules.strip_placeholders(text or ""))


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
    allowed_latin = _glossary_latin(glossary_ids)
    for field, txt, field_lang in (("reply", d.reply, lang), ("reply_ar", d.reply_ar, "ar")):
        noise = rules.garbled(txt, field_lang, allowed_latin)
        if noise:
            issues.append(f"{field} contains garbled text — {noise}; rewrite it fully in the target language")
    # Every point must be backed by evidence or glossary ids; a point without a source is a claim
    # the model made up (rule: content only from the sources).
    known = ev_ids | set(glossary_ids) | allowed
    for p in d.points:
        if not p.source_ids:
            issues.append(f'point "{p.meaning[:80]}" has no source; drop it or tie it to an evidence id')
        else:
            bad = [sid for sid in p.source_ids if sid not in known and not rules.is_covered(sid, allowed)]
            if bad:
                issues.append(f'point "{p.meaning[:60]}" cites {", ".join(bad)}, which is not in the evidence')
    if evidence and not d.points:
        issues.append("list the religious points of the reply in `points`, each with its evidence ids")
    # The reply must be in the language of the message being answered (not the sources' language).
    got = detect_confident(_strip_rendered(d.reply))
    if got and not rules.same_language(got[0], lang):
        issues.append(f"the reply is written in '{got[0]}' but must be written in '{lang}' "
                      "(the language of the seeker's message); translate the meaning, not the sources")
    # Explanations must be re-expressed, not pasted.
    for field, txt in (("reply", d.reply), ("reply_ar", d.reply_ar)):
        for e in evidence:
            if e.type in EXPLANATION_TYPES:
                n, words = rules.longest_shared_run(txt, e.text_ar)
                if n >= rules.COPY_RUN:
                    issues.append(f'{field} copies {n} words of {e.id} verbatim ("{words[:70]}…"); '
                                  "re-express the meaning in your own words for this seeker")
                    break
    if level in ("C", "D"):
        for p in rules.certainty_claims(d.reply) + rules.certainty_claims(d.reply_ar):
            issues.append(f'level {level}: remove the claim of certainty/consensus "{p}"')
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
    glossary = state.get("glossary", {})
    d = inline_ids_to_text(repair_draft(state["draft"], evidence), lang, glossary)
    # The sources of the points are citations too (the da'i sees where each idea comes from).
    point_ids = [sid for p in d.points for sid in p.source_ids]
    d = d.model_copy(update={"cited_ids": list(dict.fromkeys([*d.cited_ids, *point_ids]))})
    level = state["routing"].level
    issues = check_draft(d, evidence, lang, level, set(glossary))
    judge_down, advisory = False, []
    if not issues and settings.VERIFY_LLM_JUDGE:
        judged = _judge(d, evidence)
        judge_down = judged is None
        if judged:
            issues, advisory = judged.blocking, judged.advisory

    attempts = state.get("attempts", 1)
    # Register (not content): one rewrite if the draft sounds like a book, never a block.
    style = [] if issues else rules.boilerplate(d.reply)
    if style and attempts < settings.MAX_DRAFT_ATTEMPTS:
        issues = [f'the reply sounds like a textbook ("{style[0]}"); rewrite it as a warm chat message from the '
                  "da'i to this seeker, same points, your own words"]
        return {"issues": issues, "verdict": "retry", "retry_issues": [*state.get("retry_issues", []), *issues],
                "trace": _trace(state, "verify:style")}
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
    if level == "D":  # only reached for audience="scholar"
        note = ("🔴 مستوى D (حالة شخصية): المسودة تعرض الأدلة والقواعد العامة فقط دون حكم على حالة السائل؛ "
                "الحكم لك بعد معرفة التفاصيل. " + note)
    return {
        "verdict": "fail" if issues else "pass",
        "status": "unverified" if issues else "ok",
        "issues": [*issues, *advisory],
        "final_reply": _render(d.reply, lang, by_id),
        "final_reply_ar": _render(d.reply_ar, "ar", by_id),
        "final_draft": d,
        "note_for_dai": note,
        "citations": _citations(d, evidence, lang, glossary),
        "trace": _trace(state, "verify:judge_unavailable" if judge_down else "verify"),
    }


# ------------------------------------------------------- refer / abstain ---
def refer(state: AgentState) -> dict:
    lang, r = state["language"], state["routing"]
    if state.get("refer_reason") == "judgement":
        table = templates.REFER_SPECIALIST
        note = ("🟠 السؤال يطلب حكمًا على شخص أو فرقة أو جماعة، وهذا خارج نطاق المساعد بحسب المعيار العلمي: "
                "أُحيل السائل لأهل العلم دون إصدار حكم. " + r.reason)
    elif state.get("refer_reason") == "specialist":
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
