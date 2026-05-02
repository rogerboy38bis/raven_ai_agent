"""
Smoke tests for the Agentic-Design-Patterns module.

Run with:
    python -m raven_ai_agent.patterns.tests.test_patterns_smoke

These tests use a hand-rolled FakeProvider so they require no Frappe runtime,
no API keys, and no network.  They verify the *control flow* of each pattern,
not LLM quality.
"""
from __future__ import annotations

import json
from typing import Dict, List

from raven_ai_agent.patterns import (
    Coordinator,
    AgentSpec,
    FallbackChain,
    GoalLoop,
    Guardrails,
    Plan,
    Planner,
    RAGRetriever,
    ReflectionLoop,
    IntelligenceLayer,
)
from raven_ai_agent.patterns.guardrails import Severity


# --------------------------------------------------------------------------- #
class FakeProvider:
    """Scriptable provider that returns canned responses in order."""

    name = "fake"

    def __init__(self, scripted: List[str]):
        self.scripted = list(scripted)
        self.calls: List[Dict] = []

    def chat(self, messages, model=None, temperature=0.3, max_tokens=2000, stream=False):
        self.calls.append({"messages": messages, "temperature": temperature})
        if not self.scripted:
            return ""
        return self.scripted.pop(0)


# --------------------------------------------------------------------------- #
def test_reflection_accepts_after_revise():
    p = FakeProvider(
        scripted=[
            "draft v1",
            "VERDICT: REVISE\nISSUES:\n- needs item code\nSUGGESTIONS:\n- add code",
            "draft v2 with item code 0307",
            "VERDICT: ACCEPT\nISSUES:\nSUGGESTIONS:",
        ]
    )
    loop = ReflectionLoop(provider=p, producer_system_prompt="prod", max_iterations=2)
    res = loop.run("Build BOM for 0307", criteria=["include item code"])
    assert res.accepted, res.history
    assert "0307" in res.final_answer
    print("test_reflection_accepts_after_revise OK")


def test_planner_parses_json():
    plan_json = json.dumps(
        {
            "goal": "Take SAL-QTN-0901 to paid invoice",
            "steps": [
                {"id": 1, "intent": "diagnose", "command": "diagnose SAL-QTN-0901",
                 "depends_on": [], "rationale": "verify pipeline"},
                {"id": 2, "intent": "convert", "command": "convert quotation SAL-QTN-0901 to sales order",
                 "depends_on": [1], "rationale": "create SO"},
            ],
            "success_criteria": ["Sales Invoice paid"],
        }
    )
    p = FakeProvider(scripted=[plan_json])
    plan = Planner(p).plan("Take SAL-QTN-0901 to a paid invoice")
    assert isinstance(plan, Plan)
    assert len(plan.steps) == 2
    assert plan.steps[1].depends_on == [1]
    print("test_planner_parses_json OK")


def test_coordinator_picks_agent():
    p = FakeProvider(
        scripted=[
            json.dumps(
                {"agent": "workflow_run",
                 "instruction": "Run full cycle on SO-00752",
                 "confidence": 0.92}
            )
        ]
    )
    specs = [
        AgentSpec(name="workflow_run", description="Full 8-step cycle"),
        AgentSpec(name="morning_briefing", description="Daily briefing"),
    ]
    decision = Coordinator(p, agents=specs).decide("kick off the full cycle on SO-00752")
    assert decision.agent == "workflow_run"
    assert decision.confidence > 0.8
    print("test_coordinator_picks_agent OK")


def test_goal_loop_external_checker():
    from raven_ai_agent.patterns.goal_loop import GoalCheck

    attempts = {"n": 0}

    def checker(answer: str) -> GoalCheck:
        attempts["n"] += 1
        if "INV-001" in answer:
            return GoalCheck(satisfied=True)
        return GoalCheck(satisfied=False, unmet=["mention INV-001"])

    p = FakeProvider(scripted=["here is your invoice", "look at INV-001 it's paid"])
    loop = GoalLoop(provider=p, attempt_system_prompt="sys",
                    max_iterations=3, external_checker=checker)
    res = loop.run("explain invoice", success_criteria=["mention INV-001"])
    assert res.satisfied, res.history
    assert "INV-001" in res.final_answer
    print("test_goal_loop_external_checker OK")


def test_fallback_chain_skips_failures():
    def bad(**_): raise RuntimeError("boom")
    def empty(**_): return ""
    def ok(**_): return "answer"

    chain = FallbackChain(handlers=[("a", bad), ("b", empty), ("c", ok)])
    res = chain.run()
    assert res.chosen == "c"
    assert res.value == "answer"
    assert len(res.attempts) == 3
    print("test_fallback_chain_skips_failures OK")


def test_rag_retriever_grounds_answer():
    p = FakeProvider(scripted=["[#1] tells us the SO is SO-00752"])
    def retriever(q, k):
        return [{"content": "SO-00752 is the active sales order", "source": "AI Memory#42"}]
    rag = RAGRetriever(p, retriever=retriever)
    res = rag.answer("which SO?")
    assert res.used_context
    assert res.retrieved[0].source == "AI Memory#42"
    print("test_rag_retriever_grounds_answer OK")


def test_guardrails_blocks_copilot_mutation():
    g = Guardrails()
    report = g.check({"kind": "submit", "doctype": "Sales Invoice", "name": "SINV-1",
                      "autonomy": "copilot"})
    severities = [v.severity for v in report.violations]
    assert Severity.HIGH in severities
    assert any(v.rule == "copilot_blocks_mutation" for v in report.violations)
    print("test_guardrails_blocks_copilot_mutation OK")


def test_intelligence_layer_complexity_classifier():
    p = FakeProvider(scripted=[])
    il = IntelligenceLayer(provider=p)
    assert il.classify_complexity("complete workflow on SAL-QTN-0901").label == "planning"
    assert il.classify_complexity("audit the SO totals").label == "reflection"
    assert il.classify_complexity("according to previous sessions, what was X").label == "rag"
    assert il.classify_complexity("show pending invoices").label == "simple"
    print("test_intelligence_layer_complexity_classifier OK")


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    test_reflection_accepts_after_revise()
    test_planner_parses_json()
    test_coordinator_picks_agent()
    test_goal_loop_external_checker()
    test_fallback_chain_skips_failures()
    test_rag_retriever_grounds_answer()
    test_guardrails_blocks_copilot_mutation()
    test_intelligence_layer_complexity_classifier()
    print("\nAll pattern smoke tests passed.")
