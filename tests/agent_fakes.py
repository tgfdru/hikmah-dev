"""Scripted stand-in for the LLM so the agent graph runs offline in tests.

A script maps a stage ("analyze", "route", "generate", "judge", "translate") to
either one answer or a list of answers returned in order (for retries).
"""
from __future__ import annotations

from agent.state import Analysis, Draft, Routing


class _Bound:
    def __init__(self, fake: "FakeLLM", stage: str, raw: bool = False):
        self.fake, self.stage, self.raw = fake, stage, raw

    def invoke(self, messages):
        self.fake.calls.append((self.stage, messages))
        answer = self.fake.script[self.stage]
        if isinstance(answer, list):
            i = self.fake.counters.get(self.stage, 0)
            self.fake.counters[self.stage] = i + 1
            answer = answer[min(i, len(answer) - 1)]
        if isinstance(answer, Exception):   # simulate an endpoint error
            raise answer
        if not self.raw:
            return answer
        if isinstance(answer, dict) and "raw_args" in answer:   # simulate a malformed tool call
            raw = type("Raw", (), {"tool_calls": [{"args": answer["raw_args"]}]})()
            return {"parsed": None, "raw": raw, "parsing_error": ValueError("bad")}
        return {"parsed": answer, "raw": None, "parsing_error": None}


class _Client:
    def __init__(self, fake: "FakeLLM", stage: str):
        self.fake, self.stage = fake, stage

    def with_structured_output(self, schema, method=None, include_raw=False):
        assert method == "function_calling", "space-bunny-free needs method='function_calling'"
        return _Bound(self.fake, self.stage, raw=include_raw)

    def invoke(self, messages):
        return _Bound(self.fake, self.stage).invoke(messages)


class FakeLLM:
    def __init__(self, script: dict):
        self.script, self.calls, self.counters = script, [], {}

    def __call__(self, stage: str):
        return _Client(self, stage)

    def stages(self) -> list[str]:
        return [s for s, _ in self.calls]


def analysis(**kw) -> Analysis:
    base = dict(language="en", knowledge_level="beginner", background="unknown", tone="curious",
                core_question="لماذا يعبد المسلمون الكعبة؟", arabic_query="استقبال الكعبة في الصلاة عبادة الله",
                asks_for_hadith=False, asks_term_meaning=False, personal_case=False)
    base.update(kw)
    return Analysis(**base)


def routing(level="A", reason="سؤال تعريفي مستقر") -> Routing:
    return Routing(level=level, reason=reason)


def draft(reply="Muslims do not worship the Kaaba; they face it in prayer as Allah commanded: [[Q:2:144]]",
          reply_ar="المسلمون لا يعبدون الكعبة بل يستقبلونها في الصلاة امتثالًا لأمر الله: [[Q:2:144]]",
          cited_ids=("Q:2:144", "QA:bayyinat:9"), note="بدأت بتصحيح التصور بلطف.") -> Draft:
    return Draft(reply=reply, reply_ar=reply_ar, cited_ids=list(cited_ids), note_for_dai=note)
