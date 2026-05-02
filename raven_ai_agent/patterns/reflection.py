"""
Reflection Pattern (Chapter 4 - Iterative Loop)
================================================

The agent produces an answer, then a critic prompt evaluates it against
quality criteria. If the critique requests changes, the producer revises.
Loop until the critic accepts or max_iterations is reached.

In Raven this is most useful for:
  - BOM creator output (verify item codes / qty / UoM consistency)
  - Quotation → SO field-mapping responses
  - Pipeline diagnosis reports (Raymond anti-hallucination)
  - Data Quality Scanner explanations
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


CRITIC_SYSTEM_PROMPT = """You are a strict reviewer of ERPNext AI agent answers.
Evaluate the assistant's draft against the user's request and the supplied criteria.

Reply STRICTLY in this format:
VERDICT: ACCEPT | REVISE
ISSUES:
- <issue 1>
- <issue 2>
SUGGESTIONS:
- <concrete change 1>
- <concrete change 2>

Use VERDICT: ACCEPT only when the draft is correct, complete, and free of hallucinations.
Otherwise VERDICT: REVISE with specific issues."""


@dataclass
class ReflectionResult:
    final_answer: str
    iterations: int
    history: List[Dict] = field(default_factory=list)
    accepted: bool = False


class ReflectionLoop:
    """Producer/Critic loop with bounded iteration."""

    def __init__(
        self,
        provider,
        producer_system_prompt: str,
        critic_system_prompt: str = CRITIC_SYSTEM_PROMPT,
        max_iterations: int = 3,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ):
        self.provider = provider
        self.producer_system_prompt = producer_system_prompt
        self.critic_system_prompt = critic_system_prompt
        self.max_iterations = max_iterations
        self.temperature = temperature
        self.max_tokens = max_tokens

    def run(
        self,
        user_request: str,
        criteria: Optional[List[str]] = None,
        context: Optional[str] = None,
    ) -> ReflectionResult:
        criteria_block = ""
        if criteria:
            criteria_block = "\n\nCriteria the answer MUST satisfy:\n" + "\n".join(
                f"- {c}" for c in criteria
            )
        ctx_block = f"\n\nContext:\n{context}" if context else ""

        producer_messages = [
            {"role": "system", "content": self.producer_system_prompt + criteria_block},
            {"role": "user", "content": user_request + ctx_block},
        ]

        history: List[Dict] = []
        draft = self._chat(producer_messages)
        history.append({"role": "producer", "content": draft, "iteration": 0})

        for i in range(1, self.max_iterations + 1):
            critic_messages = [
                {"role": "system", "content": self.critic_system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"User request:\n{user_request}{ctx_block}{criteria_block}\n\n"
                        f"Draft answer:\n{draft}"
                    ),
                },
            ]
            verdict_text = self._chat(critic_messages)
            history.append({"role": "critic", "content": verdict_text, "iteration": i})

            verdict, suggestions = self._parse_verdict(verdict_text)
            if verdict == "ACCEPT":
                return ReflectionResult(
                    final_answer=draft, iterations=i, history=history, accepted=True
                )

            # Revise
            producer_messages.append({"role": "assistant", "content": draft})
            producer_messages.append(
                {
                    "role": "user",
                    "content": (
                        "A reviewer flagged the following issues. "
                        "Produce a revised answer that addresses every point. "
                        "Reply with the revised answer only.\n\n"
                        + verdict_text
                    ),
                }
            )
            draft = self._chat(producer_messages)
            history.append({"role": "producer", "content": draft, "iteration": i})

        logger.info(
            "ReflectionLoop hit max_iterations=%s without ACCEPT", self.max_iterations
        )
        return ReflectionResult(
            final_answer=draft,
            iterations=self.max_iterations,
            history=history,
            accepted=False,
        )

    # ------------------------------------------------------------------ #
    def _chat(self, messages: List[Dict]) -> str:
        return self.provider.chat(
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

    @staticmethod
    def _parse_verdict(text: str) -> tuple[str, str]:
        verdict = "REVISE"
        for line in text.splitlines():
            stripped = line.strip().upper()
            if stripped.startswith("VERDICT:"):
                if "ACCEPT" in stripped:
                    verdict = "ACCEPT"
                break
        return verdict, text
