"""
Planning Pattern (Chapter 6)
============================

Decomposes a complex user goal into ordered, individually executable steps
expressed as ERPNext-aware command strings.  The planner outputs a strict
JSON document so the existing `command_router` / `multi_agent_router` can
pick each step up without a second LLM hop.

Typical Raven use cases:
  * "Take quotation SAL-QTN-0901 all the way to a paid invoice"
  * "Diagnose SO-00752, fix any pipeline gaps, then send a delivery note"
  * "Scan data quality on Customers, summarise, and create the top 5 fixes"
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


PLANNER_SYSTEM_PROMPT = """You are the Planner for the Raven AI Agent on ERPNext.

Given a user goal, decompose it into the SMALLEST sequence of concrete steps
that the existing Raven command router can execute. Each step MUST be one
documented command (e.g. 'diagnose SAL-QTN-0901', 'convert quotation SAL-QTN-0901 to sales order',
'create work order from SO-00752', 'invoice from SO-00752', 'submit invoice SINV-00123').

Reply ONLY with valid JSON in this exact schema:
{
  "goal": "<restated goal>",
  "steps": [
    {
      "id": 1,
      "intent": "<short label, e.g. diagnose>",
      "command": "<exact command string>",
      "depends_on": [],
      "rationale": "<one sentence>"
    }
  ],
  "success_criteria": ["<criterion 1>", "<criterion 2>"]
}

Rules:
- Steps must be ordered.  Use depends_on to express prerequisites.
- Never invent document IDs that were not given.
- Prefer the smallest plan that achieves the goal.
- Output JSON ONLY — no prose, no markdown fences."""


@dataclass
class PlanStep:
    id: int
    intent: str
    command: str
    depends_on: List[int] = field(default_factory=list)
    rationale: str = ""

    @classmethod
    def from_dict(cls, d: Dict) -> "PlanStep":
        return cls(
            id=int(d.get("id", 0)),
            intent=str(d.get("intent", "")),
            command=str(d.get("command", "")).strip(),
            depends_on=[int(x) for x in d.get("depends_on", []) or []],
            rationale=str(d.get("rationale", "")),
        )


@dataclass
class Plan:
    goal: str
    steps: List[PlanStep]
    success_criteria: List[str] = field(default_factory=list)
    raw: str = ""

    def is_empty(self) -> bool:
        return not self.steps

    def as_markdown(self) -> str:
        lines = [f"**Goal:** {self.goal}", "", "**Plan:**"]
        for s in self.steps:
            dep = f" (after {s.depends_on})" if s.depends_on else ""
            lines.append(f"{s.id}. `{s.command}` — {s.rationale}{dep}")
        if self.success_criteria:
            lines.append("\n**Done when:**")
            for c in self.success_criteria:
                lines.append(f"- {c}")
        return "\n".join(lines)


class Planner:
    """LLM-driven planner that emits a strict JSON Plan."""

    def __init__(
        self,
        provider,
        system_prompt: str = PLANNER_SYSTEM_PROMPT,
        temperature: float = 0.1,
        max_tokens: int = 1500,
    ):
        self.provider = provider
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.max_tokens = max_tokens

    def plan(self, goal: str, context: Optional[str] = None) -> Plan:
        ctx = f"\n\nContext / known IDs:\n{context}" if context else ""
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Goal:\n{goal}{ctx}"},
        ]
        raw = self.provider.chat(
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return self._parse(raw, goal)

    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse(raw: str, goal: str) -> Plan:
        text = raw.strip()
        # Strip ```json fences if a model adds them despite the instruction.
        fence = re.match(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
        if fence:
            text = fence.group(1).strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Planner output was not valid JSON; returning empty plan")
            return Plan(goal=goal, steps=[], raw=raw)

        steps = [PlanStep.from_dict(s) for s in data.get("steps", []) or []]
        return Plan(
            goal=str(data.get("goal", goal)),
            steps=steps,
            success_criteria=list(data.get("success_criteria", []) or []),
            raw=raw,
        )
