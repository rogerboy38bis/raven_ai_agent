"""
Agentic Design Patterns for Raven AI Agent
==========================================

Implementation of the patterns from Antonio Gulli's
"Agentic Design Patterns: A Hands-On Guide to Building Intelligent Systems"
adapted to Raven's Frappe/ERPNext environment.

Provider-agnostic: every pattern accepts an `LLMProvider` instance from
`raven_ai_agent.providers`, so all five providers (OpenAI, DeepSeek, Claude,
MiniMax, Ollama) work transparently.

Patterns included
-----------------
- reflection.ReflectionLoop ......... Chapter 4: self-critique + refine
- planner.Planner ................... Chapter 6: task decomposition
- coordinator.Coordinator ........... Chapter 7: multi-agent delegation
- goal_loop.GoalLoop ................ Chapter 11: goal + iteration until satisfied
- fallback.FallbackChain ............ Chapter 12: graceful provider degradation
- rag_retriever.RAGRetriever ........ Chapter 14: ground answers in memories/docs
- guardrails.Guardrails ............. Chapter 18: validate before destructive ops
"""

from .reflection import ReflectionLoop
from .planner import Planner, Plan, PlanStep
from .coordinator import Coordinator, AgentSpec
from .goal_loop import GoalLoop, GoalCheck
from .fallback import FallbackChain
from .rag_retriever import RAGRetriever
from .guardrails import Guardrails, GuardrailViolation
from .intelligence import IntelligenceLayer, Complexity

__all__ = [
    "ReflectionLoop",
    "Planner",
    "Plan",
    "PlanStep",
    "Coordinator",
    "AgentSpec",
    "GoalLoop",
    "GoalCheck",
    "FallbackChain",
    "RAGRetriever",
    "Guardrails",
    "GuardrailViolation",
    "IntelligenceLayer",
    "Complexity",
]
