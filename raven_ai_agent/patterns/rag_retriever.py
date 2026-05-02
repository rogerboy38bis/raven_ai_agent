"""
Knowledge Retrieval / RAG Pattern (Chapter 14)
==============================================

Thin wrapper that turns Raven's existing `VectorStore` (and the keyword
fallback in `MemoryMixin.search_memories`) into a full retrieve-and-ground
helper for any prompt.

Pipeline:
    query → retrieve top-k → format as numbered context block → answer with
    explicit citations of the form [#1], [#2] which are then expanded into
    "AI Memory" links / source labels.

If the workspace `VectorStore` is unavailable (e.g. running outside Frappe
during tests), pass any retriever callable that returns a list of dicts
with at least {"content": str, "source": str}.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

RAG_SYSTEM_PROMPT = """You answer ERPNext questions for Raven users.
You MUST ground every factual claim in the supplied numbered context.
Cite sources inline as [#1], [#2], etc.
If the context does not contain enough information, say so plainly —
do NOT invent document IDs, totals or dates."""


@dataclass
class Retrieved:
    content: str
    source: str
    score: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RAGResult:
    answer: str
    retrieved: List[Retrieved]
    used_context: bool


class RAGRetriever:
    def __init__(
        self,
        provider,
        retriever: Callable[[str, int], List[Dict]],
        system_prompt: str = RAG_SYSTEM_PROMPT,
        top_k: int = 5,
        temperature: float = 0.2,
        max_tokens: int = 1500,
    ):
        """retriever(query, k) -> list of dicts with at least
        'content' and 'source' keys (extra keys preserved in `extra`)."""
        self.provider = provider
        self.retriever = retriever
        self.system_prompt = system_prompt
        self.top_k = top_k
        self.temperature = temperature
        self.max_tokens = max_tokens

    def answer(self, query: str, extra_context: Optional[str] = None) -> RAGResult:
        try:
            raw_hits = self.retriever(query, self.top_k) or []
        except Exception as exc:  # pragma: no cover
            logger.warning("RAG retriever raised: %s", exc)
            raw_hits = []

        retrieved: List[Retrieved] = []
        for h in raw_hits:
            if not isinstance(h, dict):
                continue
            retrieved.append(
                Retrieved(
                    content=str(h.get("content", "")).strip(),
                    source=str(h.get("source") or h.get("name") or "unknown"),
                    score=float(h.get("score", h.get("similarity", 0.0)) or 0.0),
                    extra={k: v for k, v in h.items() if k not in ("content", "source")},
                )
            )

        ctx_block = self._format_context(retrieved)
        extra_block = f"\n\nAdditional context:\n{extra_context}" if extra_context else ""

        messages = [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": (
                    f"Question:\n{query}\n\nNumbered context:\n{ctx_block}{extra_block}"
                ),
            },
        ]
        answer = self.provider.chat(
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return RAGResult(answer=answer, retrieved=retrieved, used_context=bool(retrieved))

    # ------------------------------------------------------------------ #
    @staticmethod
    def _format_context(items: List[Retrieved]) -> str:
        if not items:
            return "(no relevant context found)"
        lines = []
        for i, it in enumerate(items, 1):
            lines.append(f"[#{i}] (source: {it.source}) {it.content}")
        return "\n".join(lines)
