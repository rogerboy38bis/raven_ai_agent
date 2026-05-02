"""
Multi-Agent Coordinator Pattern (Chapter 7)
===========================================

A single LLM call decides which specialist agent should handle a request,
based on a registry of agent specs. This is the natural-language complement
to Raven's existing regex-based `multi_agent_router`: when the regex
patterns miss, fall back to the Coordinator for a semantic match.

It returns the agent name + a sub-prompt rewritten for that agent so the
specialist receives a focused, well-scoped task.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentSpec:
    """Description of one specialist agent the Coordinator can route to."""

    name: str
    description: str
    examples: List[str] = field(default_factory=list)
    handler: Optional[Callable[[str, Dict], str]] = None  # called with (subprompt, context)


COORDINATOR_SYSTEM_PROMPT = """You are the Coordinator. Your only job is to pick
the single best specialist agent for a user request and rewrite the request
as a focused instruction for that agent.

Reply ONLY with strict JSON:
{"agent": "<name from the catalog>", "instruction": "<rewritten request>", "confidence": 0.0-1.0}

If no agent fits, respond with {"agent": "none", "instruction": "<verbatim>", "confidence": 0.0}."""


@dataclass
class CoordinatorDecision:
    agent: str
    instruction: str
    confidence: float
    raw: str = ""


class Coordinator:
    def __init__(
        self,
        provider,
        agents: List[AgentSpec],
        system_prompt: str = COORDINATOR_SYSTEM_PROMPT,
        temperature: float = 0.0,
        max_tokens: int = 600,
    ):
        self.provider = provider
        self.agents = {a.name: a for a in agents}
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.max_tokens = max_tokens

    # ------------------------------------------------------------------ #
    def decide(self, request: str, context: Optional[str] = None) -> CoordinatorDecision:
        catalog = "\n".join(
            f"- {a.name}: {a.description}"
            + (f"  Examples: {a.examples}" if a.examples else "")
            for a in self.agents.values()
        )
        ctx_block = f"\n\nContext:\n{context}" if context else ""
        messages = [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": (
                    f"Available agents:\n{catalog}\n\n"
                    f"User request:\n{request}{ctx_block}"
                ),
            },
        ]
        raw = self.provider.chat(
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return self._parse(raw, fallback=request)

    def dispatch(
        self, request: str, context: Optional[Dict] = None
    ) -> Dict:
        """Run decide() then invoke the matching agent's handler if any."""
        decision = self.decide(request, context=str(context) if context else None)
        agent_spec = self.agents.get(decision.agent)
        if not agent_spec or not agent_spec.handler:
            return {
                "decision": decision,
                "result": None,
                "handled": False,
            }
        result = agent_spec.handler(decision.instruction, context or {})
        return {"decision": decision, "result": result, "handled": True}

    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse(raw: str, fallback: str) -> CoordinatorDecision:
        text = raw.strip()
        fence = re.match(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
        if fence:
            text = fence.group(1).strip()
        try:
            data = json.loads(text)
            return CoordinatorDecision(
                agent=str(data.get("agent", "none")),
                instruction=str(data.get("instruction", fallback)),
                confidence=float(data.get("confidence", 0.0)),
                raw=raw,
            )
        except (json.JSONDecodeError, ValueError, TypeError):
            logger.warning("Coordinator output not parseable; defaulting to none")
            return CoordinatorDecision(
                agent="none", instruction=fallback, confidence=0.0, raw=raw
            )
