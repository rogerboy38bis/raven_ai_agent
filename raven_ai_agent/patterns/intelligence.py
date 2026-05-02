"""
IntelligenceLayer
=================

A thin orchestrator that bundles the Agentic-Design-Patterns primitives
into ergonomic, opt-in helpers used by `RaymondLucyAgentV2`.

The goal is to keep the V2 agent's `process_query` lean: it consults the
intelligence layer at four well-defined extension points:

  1. classify_complexity()  → simple | planning | reflection | rag
  2. plan(query)            → Plan
  3. answer_with_rag(query) → grounded answer with citations
  4. refine(query, draft)   → critic-driven revision
  5. guard(action)          → guardrails report before mutating ERPNext

The layer is provider-agnostic; it composes whatever LLMProvider the
agent already has.  Frappe is NOT imported here so the patterns can be
unit-tested without a Frappe runtime.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from .reflection import ReflectionLoop, ReflectionResult
from .planner import Planner, Plan
from .coordinator import Coordinator, AgentSpec, CoordinatorDecision
from .goal_loop import GoalLoop, GoalLoopResult
from .fallback import FallbackChain, provider_chain
from .rag_retriever import RAGRetriever, RAGResult
from .guardrails import Guardrails, GuardrailReport

logger = logging.getLogger(__name__)


COMPLEXITY_HINTS = {
    "planning": (
        "complete workflow",
        "all the way to",
        "full cycle",
        "diagnose and fix",
        "then ",
        " then ",
        "and then",
        "execute workflow",
    ),
    "reflection": (
        "verify",
        "double check",
        "audit",
        "validate",
        "make sure",
    ),
    "rag": (
        "what did we",
        "remember when",
        "find the memory",
        "according to",
        "based on previous",
    ),
}


@dataclass
class Complexity:
    label: str   # "simple" | "planning" | "reflection" | "rag"
    reasons: List[str]


class IntelligenceLayer:
    """High-level façade over the patterns/ primitives."""

    def __init__(
        self,
        provider,
        retriever: Optional[Callable[[str, int], List[Dict]]] = None,
        secondary_providers: Optional[Dict[str, Any]] = None,
        producer_system_prompt: str = "You are Raymond-Lucy, a careful ERPNext copilot.",
    ):
        self.provider = provider
        self.retriever = retriever
        self.secondary_providers = secondary_providers or {}
        self.producer_system_prompt = producer_system_prompt
        self.guardrails = Guardrails()

    # ------------------------------------------------------------------ #
    # 1. Cheap classifier — rule based, no LLM hop
    # ------------------------------------------------------------------ #
    def classify_complexity(self, query: str) -> Complexity:
        q = (query or "").lower()
        reasons: List[str] = []
        for label, hints in COMPLEXITY_HINTS.items():
            if any(h in q for h in hints):
                reasons.append(label)
        if "planning" in reasons:
            return Complexity("planning", reasons)
        if "reflection" in reasons:
            return Complexity("reflection", reasons)
        if "rag" in reasons:
            return Complexity("rag", reasons)
        return Complexity("simple", reasons)

    # ------------------------------------------------------------------ #
    # 2. Planning
    # ------------------------------------------------------------------ #
    def plan(self, goal: str, context: Optional[str] = None) -> Plan:
        return Planner(self.provider).plan(goal=goal, context=context)

    # ------------------------------------------------------------------ #
    # 3. RAG
    # ------------------------------------------------------------------ #
    def answer_with_rag(
        self, query: str, extra_context: Optional[str] = None, top_k: int = 5
    ) -> Optional[RAGResult]:
        if self.retriever is None:
            return None
        rag = RAGRetriever(self.provider, retriever=self.retriever, top_k=top_k)
        return rag.answer(query, extra_context=extra_context)

    # ------------------------------------------------------------------ #
    # 4. Reflection / refinement
    # ------------------------------------------------------------------ #
    def refine(
        self,
        query: str,
        draft: str,
        criteria: Optional[List[str]] = None,
        max_iterations: int = 2,
    ) -> ReflectionResult:
        loop = ReflectionLoop(
            provider=self.provider,
            producer_system_prompt=self.producer_system_prompt,
            max_iterations=max_iterations,
        )
        # Seed the loop with the existing draft so the first iteration is the critique.
        return loop.run(
            user_request=query,
            criteria=criteria,
            context=f"Existing draft to refine:\n{draft}",
        )

    # ------------------------------------------------------------------ #
    # 5. Goal loop  (deterministic checker injection point)
    # ------------------------------------------------------------------ #
    def goal_loop(
        self,
        goal: str,
        criteria: List[str],
        external_checker: Optional[Callable] = None,
        max_iterations: int = 3,
    ) -> GoalLoopResult:
        loop = GoalLoop(
            provider=self.provider,
            attempt_system_prompt=self.producer_system_prompt,
            max_iterations=max_iterations,
            external_checker=external_checker,
        )
        return loop.run(goal=goal, success_criteria=criteria)

    # ------------------------------------------------------------------ #
    # 6. Coordinator (semantic agent routing)
    # ------------------------------------------------------------------ #
    def coordinator(self, agents: List[AgentSpec]) -> Coordinator:
        return Coordinator(self.provider, agents=agents)

    # ------------------------------------------------------------------ #
    # 7. Provider fallback
    # ------------------------------------------------------------------ #
    def chat_with_fallback(
        self, messages: List[Dict], order: Optional[List[str]] = None, **kw
    ) -> Dict:
        providers = {self.provider.name: self.provider, **self.secondary_providers}
        order = order or [self.provider.name] + [
            n for n in self.secondary_providers if n != self.provider.name
        ]
        chain = provider_chain(providers, order, **kw)
        result = chain.run(messages=messages)
        return {
            "answer": result.value,
            "chosen": result.chosen,
            "attempts": [a.__dict__ for a in result.attempts],
        }

    # ------------------------------------------------------------------ #
    # 8. Guardrails
    # ------------------------------------------------------------------ #
    def guard(self, action: Dict[str, Any]) -> GuardrailReport:
        return self.guardrails.check(action)
