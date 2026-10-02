"""Scripted stand-in for the LLM so the agent graph runs offline in tests.

A script maps a stage ("analyze", "route", "generate", "judge", "translate") to
either one answer or a list of answers returned in order (for retries).
"""
from __future__ import annotations

from agent.state import Analysis, Draft, Routing


class _Bound:
    def __init__(self, fake: "FakeLLM", stage: str):
        self.fake, self.stage = fake, stage

    def invoke(self, messages):
        self.fake.calls.append((self.stage, messages))
        answer = self.fake.script[self.stage]
        if isinstance(answer, list):
            i = self.fake.counters.get(self.stage, 0)
            self.fake.counters[self.stage] = i + 1
            answer = answer[min(i, len(answer) - 1)]
        return answer


class _Client:
    def __init__(self, fake: "FakeLLM", stage: str):
        self.fake, self.stage = fake, stage

    def with_structured_output(self, schema, method=None):
        assert method == "function_calling", "space-bunny-free needs method='function_calling'"
        return _Bound(self.fake, self.stage)

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
                asks_for_hadith=False, personal_case=False)
    base.update(kw)
    return Analysis(**base)


def routing(level="A", reason="سؤال تعريفي مستقر") -> Routing:
    return Routing(level=level, reason=reason)


def draft(reply="Muslims do not worship the Kaaba; they face it in prayer as Allah commanded: [[Q:2:144]]",
          reply_ar="المسلمون لا يعبدون الكعبة بل يستقبلونها في الصلاة امتثالًا لأمر الله: [[Q:2:144]]",
          cited_ids=("Q:2:144", "QA:bayyinat:9"), note="بدأت بتصحيح التصور بلطف.") -> Draft:
    return Draft(reply=reply, reply_ar=reply_ar, cited_ids=list(cited_ids), note_for_dai=note)
