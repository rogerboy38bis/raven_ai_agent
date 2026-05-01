"""
Exception Handling / Fallback Pattern (Chapter 12)
==================================================

Tries a primary callable; if it raises or returns a "soft failure" (None /
empty / configurable), it falls through to the next handler.  Every attempt
is logged with timing so cost/latency can be inspected.

Two ready-made factories:
  - provider_chain():  build a fallback chain across LLM providers
                        (OpenAI → DeepSeek → Claude → MiniMax → Ollama)
  - tool_chain():      generic chain over arbitrary callables

The pattern is deliberately tiny — Raven already has retry/backoff at the
HTTP layer; this lives a level higher and is about *strategy* fallback,
not network retry.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


@dataclass
class AttemptLog:
    name: str
    ok: bool
    duration_ms: int
    error: Optional[str] = None


@dataclass
class FallbackResult:
    value: Any
    chosen: Optional[str]
    attempts: List[AttemptLog] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        return self.chosen is not None


class FallbackChain:
    """Run callables in order until one succeeds.

    Each handler is a (name, callable) tuple; the callable receives **kwargs.
    A handler is considered successful unless it raises or `is_failure(value)`
    returns True.
    """

    def __init__(
        self,
        handlers: Sequence,
        is_failure: Callable[[Any], bool] = lambda v: v in (None, "", [], {}),
    ):
        self.handlers: List = list(handlers)
        self.is_failure = is_failure

    def run(self, **kwargs) -> FallbackResult:
        attempts: List[AttemptLog] = []
        for name, handler in self.handlers:
            t0 = time.perf_counter()
            try:
                value = handler(**kwargs)
            except Exception as exc:  # broad on purpose: we want to fall through
                duration = int((time.perf_counter() - t0) * 1000)
                logger.warning("FallbackChain handler %s raised: %s", name, exc)
                attempts.append(
                    AttemptLog(name=name, ok=False, duration_ms=duration, error=str(exc))
                )
                continue
            duration = int((time.perf_counter() - t0) * 1000)
            if self.is_failure(value):
                attempts.append(
                    AttemptLog(name=name, ok=False, duration_ms=duration, error="empty")
                )
                continue
            attempts.append(AttemptLog(name=name, ok=True, duration_ms=duration))
            return FallbackResult(value=value, chosen=name, attempts=attempts)

        return FallbackResult(value=None, chosen=None, attempts=attempts)


# ------------------------------------------------------------------ #
# Convenience factories
# ------------------------------------------------------------------ #
def provider_chain(
    providers: Dict[str, Any],
    order: Sequence[str],
    **chat_kwargs,
) -> FallbackChain:
    """Build a FallbackChain that calls .chat() across providers in `order`.

    Usage:
        chain = provider_chain(
            providers={"openai": p1, "deepseek": p2, "claude": p3},
            order=["openai", "deepseek", "claude"],
            temperature=0.3, max_tokens=2000,
        )
        result = chain.run(messages=[...])

    The chain returns the first non-empty string response.
    """
    handlers = []
    for name in order:
        prov = providers.get(name)
        if prov is None:
            continue

        def make_handler(p):
            def _call(**kwargs):
                merged = dict(chat_kwargs)
                merged.update(kwargs)
                return p.chat(**merged)
            return _call

        handlers.append((name, make_handler(prov)))
    return FallbackChain(handlers=handlers)


def tool_chain(handlers: Sequence) -> FallbackChain:
    """Generic chain over arbitrary callables. Pass [(name, fn), ...]."""
    return FallbackChain(handlers=handlers)
