"""
Goal Setting & Iteration Pattern (Chapter 11)
=============================================

The agent is given an explicit GOAL plus a list of SUCCESS CRITERIA.
After each attempt, an LLM checker decides whether every criterion is met.
If not, the unmet criteria are fed back into the next iteration as a
focused critique.  Difference vs. ReflectionLoop: the goal/criteria are
fixed inputs, and the loop terminates strictly on criteria satisfaction.

Best fit for Raven:
  * Anti-hallucination: "Every doc ID mentioned must exist in ERPNext"
  * CFDI compliance checks before submitting an invoice
  * Pipeline diagnosis until all 8 workflow steps report green
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


CHECKER_SYSTEM_PROMPT = """You verify whether an agent's answer satisfies every
success criterion. Reply STRICTLY in JSON:
{"satisfied": true|false, "unmet": ["<criterion text>", ...], "notes": "<short>"}"""


@dataclass
class GoalCheck:
    satisfied: bool
    unmet: List[str] = field(default_factory=list)
    notes: str = ""
    raw: str = ""


@dataclass
class GoalLoopResult:
    final_answer: str
    iterations: int
    satisfied: bool
    last_check: Optional[GoalCheck] = None
    history: List[Dict] = field(default_factory=list)


class GoalLoop:
    """Run an attempt → check → refine loop until criteria are met."""

    def __init__(
        self,
        provider,
        attempt_system_prompt: str,
        checker_system_prompt: str = CHECKER_SYSTEM_PROMPT,
        max_iterations: int = 4,
        temperature: float = 0.2,
        max_tokens: int = 2000,
        external_checker: Optional[Callable[[str], GoalCheck]] = None,
    ):
        """external_checker, when provided, is used INSTEAD of the LLM checker.
        This is how you wire deterministic ERPNext validation (e.g. doc-exists,
        sum totals, CFDI fields) into the loop."""
        self.provider = provider
        self.attempt_system_prompt = attempt_system_prompt
        self.checker_system_prompt = checker_system_prompt
        self.max_iterations = max_iterations
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.external_checker = external_checker

    def run(
        self,
        goal: str,
        success_criteria: List[str],
        context: Optional[str] = None,
    ) -> GoalLoopResult:
        criteria_block = "\n".join(f"- {c}" for c in success_criteria)
        ctx_block = f"\n\nContext:\n{context}" if context else ""

        messages = [
            {"role": "system", "content": self.attempt_system_prompt},
            {
                "role": "user",
                "content": (
                    f"Goal:\n{goal}\n\nSuccess criteria (ALL must be met):\n"
                    f"{criteria_block}{ctx_block}"
                ),
            },
        ]

        history: List[Dict] = []
        answer = self._chat(messages)
        history.append({"role": "agent", "content": answer, "iteration": 0})

        last_check: Optional[GoalCheck] = None
        for i in range(1, self.max_iterations + 1):
            check = self._check(goal, success_criteria, answer)
            last_check = check
            history.append({"role": "checker", "content": check.raw, "iteration": i})
            if check.satisfied:
                return GoalLoopResult(
                    final_answer=answer,
                    iterations=i,
                    satisfied=True,
                    last_check=check,
                    history=history,
                )

            unmet = "\n".join(f"- {c}" for c in check.unmet) or "(see notes)"
            messages.append({"role": "assistant", "content": answer})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Some success criteria are NOT YET MET. Revise the answer "
                        "so that every criterion is satisfied. Reply with the "
                        "revised answer only.\n\n"
                        f"Unmet criteria:\n{unmet}\n\nNotes: {check.notes}"
                    ),
                }
            )
            answer = self._chat(messages)
            history.append({"role": "agent", "content": answer, "iteration": i})

        return GoalLoopResult(
            final_answer=answer,
            iterations=self.max_iterations,
            satisfied=False,
            last_check=last_check,
            history=history,
        )

    # ------------------------------------------------------------------ #
    def _chat(self, messages: List[Dict]) -> str:
        return self.provider.chat(
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

    def _check(self, goal: str, criteria: List[str], answer: str) -> GoalCheck:
        if self.external_checker is not None:
            return self.external_checker(answer)

        criteria_block = "\n".join(f"- {c}" for c in criteria)
        messages = [
            {"role": "system", "content": self.checker_system_prompt},
            {
                "role": "user",
                "content": (
                    f"Goal:\n{goal}\n\nCriteria:\n{criteria_block}\n\nAnswer:\n{answer}"
                ),
            },
        ]
        raw = self.provider.chat(
            messages=messages,
            temperature=0.0,
            max_tokens=600,
        )
        return self._parse(raw)

    @staticmethod
    def _parse(raw: str) -> GoalCheck:
        text = raw.strip()
        fence = re.match(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
        if fence:
            text = fence.group(1).strip()
        try:
            data = json.loads(text)
            return GoalCheck(
                satisfied=bool(data.get("satisfied", False)),
                unmet=list(data.get("unmet", []) or []),
                notes=str(data.get("notes", "")),
                raw=raw,
            )
        except json.JSONDecodeError:
            return GoalCheck(satisfied=False, unmet=[], notes="parse_error", raw=raw)
