"""
Agent Supervisor (Option C)
===========================

A thin supervision layer that wraps Raven's existing per-bot dispatch in
``router.handle_raven_message`` with the Agentic-Design-Patterns
``IntelligenceLayer``.  It does NOT replace any agent (V1, V2, ManufacturingAgent,
PaymentAgent, IoTAgent, ...) — every bot keeps running exactly as it does today.
The supervisor only adds:

  * pre-dispatch:   Guardrails  +  RAG short-circuit  +  Plan injection
  * post-dispatch:  Reflection (post-revise)         + telemetry

When the env flag ``RAVEN_INTELLIGENCE_LAYER`` is unset, both functions are
transparent passthroughs — so flipping the flag off is a single-step rollback.

Two public functions
--------------------
``pre_supervise(query, user, bot_name)``
    Runs BEFORE the bot dispatch.  Returns a dict:
        {
          "short_circuit": Optional[dict],   # if not None, return this immediately
          "enriched_query": str,             # query the bot should actually receive
          "complexity": str,
          "guardrails": GuardrailReport | None,
        }

``supervise(result, query, user, bot_name, complexity)``
    Runs AFTER the bot dispatch.  Returns the (possibly enriched) result dict.

Both are safe to call when patterns are not installed — they fall back to no-op.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import frappe

# Patterns are an optional dependency at runtime; never crash if missing.
try:
    from raven_ai_agent.patterns import IntelligenceLayer
    _PATTERNS_AVAILABLE = True
except Exception:  # noqa: BLE001
    IntelligenceLayer = None  # type: ignore[assignment]
    _PATTERNS_AVAILABLE = False


# Bots that produce free-form natural-language answers and benefit MOST from
# Reflection / RAG.  Bots returning structured workflow output (manufacturing,
# payment, IoT, validator) are still pre-checked but NOT post-revised — their
# responses are typically deterministic JSON-style messages.
_NL_BOTS = {"sales_order_bot_default", "sales_order_follow_up", "rnd_bot", "executive"}

# Bots whose intent IS already a destructive action — Guardrails should always
# inspect them.  The bot_name "_default" maps to the SkillRouter / V1 fallback.
_MUTATING_BOTS = {
    "manufacturing_bot",
    "payment_bot",
    "workflow_orchestrator",
    "sales_order_follow_up",
    "_default",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def is_enabled() -> bool:
    """True when the intelligence layer should run for this request."""
    if not _PATTERNS_AVAILABLE:
        return False
    flag = os.environ.get("RAVEN_INTELLIGENCE_LAYER", "").strip().lower()
    if flag in {"1", "true", "yes", "on"}:
        return True
    # Per-site fallback
    try:
        return bool(
            frappe.db.get_single_value("AI Agent Settings", "intelligence_layer_enabled")
        )
    except Exception:  # noqa: BLE001
        return False


def pre_supervise(query: str, user: str, bot_name: Optional[str]) -> Dict[str, Any]:
    """Pre-dispatch supervision.  Cheap, never raises.

    Returns a dict with:
        short_circuit  - if set, caller should skip bot dispatch and use this
        enriched_query - the query the bot should receive (may be unchanged)
        complexity     - "simple" | "rag" | "planning" | "reflection"
        guardrails     - GuardrailReport or None
    """
    base = {
        "short_circuit": None,
        "enriched_query": query,
        "complexity": "simple",
        "guardrails": None,
    }
    if not is_enabled():
        return base

    intel = _get_layer(user)
    if intel is None:
        return base

    # 1. Classify (rule-based, free)
    try:
        complexity = intel.classify_complexity(query).label
    except Exception as exc:  # noqa: BLE001
        frappe.logger().debug(f"[AgentSupervisor] classify failed: {exc}")
        complexity = "simple"
    base["complexity"] = complexity

    # 2. Guardrails on the proposed action.  We only have a coarse description
    #    (bot_name + query); deterministic doctype/name resolution still
    #    happens inside the bot.  This catches obvious copilot-mutation
    #    attempts and bulk-without-ack early.
    try:
        report = intel.guard(
            {
                "kind": _action_kind(bot_name, query),
                "doctype": _guess_doctype(query),
                "name": _guess_doc_name(query),
                "autonomy": _autonomy_from_query(query),
                "bulk_count": _guess_bulk_count(query),
            }
        )
        base["guardrails"] = report
        if report.has_high and _autonomy_from_query(query) == "agent":
            # Hard block before we even touch the bot.
            base["short_circuit"] = {
                "success": False,
                "response": (
                    "Blocked by Guardrails before dispatch:\n\n" + report.format()
                ),
                "supervisor": {
                    "blocked": True,
                    "complexity": complexity,
                    "guardrails": [v.__dict__ for v in report.violations],
                },
            }
            # Bug Reporter: a High guardrail block under autonomy=agent is
            # exactly the kind of incident developers want to know about.
            try:
                from raven_ai_agent.bug_reporter import capture as _capture_bug
                _capture_bug(
                    severity="High",
                    bot=bot_name,
                    intent=bot_name,
                    user=user,
                    query=query,
                    failure_class="guardrail_block",
                    result_text=report.format(),
                    supervisor_meta={
                        "complexity": complexity,
                        "guardrails": [v.__dict__ for v in report.violations],
                    },
                )
            except Exception:
                pass
            return base
    except Exception as exc:  # noqa: BLE001
        frappe.logger().debug(f"[AgentSupervisor] guardrails failed: {exc}")

    # 3. RAG short-circuit: only for the natural-language fallback path.
    if complexity == "rag" and bot_name in (None, "", "sales_order_bot"):
        try:
            rag_result = intel.answer_with_rag(query, top_k=5)
            if rag_result and rag_result.used_context:
                base["short_circuit"] = {
                    "success": True,
                    "response": (
                        "[CONFIDENCE: HIGH] [PATTERN: RAG]\n\n" + rag_result.answer
                    ),
                    "supervisor": {
                        "pattern": "rag",
                        "complexity": "rag",
                        "sources": [r.source for r in rag_result.retrieved],
                    },
                }
                return base
        except Exception as exc:  # noqa: BLE001
            frappe.logger().debug(f"[AgentSupervisor] RAG failed: {exc}")

    # 4. Plan injection: prepend a numbered backbone for multi-step requests.
    if complexity == "planning":
        try:
            plan = intel.plan(goal=query)
            if not plan.is_empty():
                base["enriched_query"] = (
                    f"{query}\n\n"
                    "[Supervisor: suggested plan from Planner pattern]\n"
                    f"{plan.as_markdown()}"
                )
        except Exception as exc:  # noqa: BLE001
            frappe.logger().debug(f"[AgentSupervisor] plan failed: {exc}")

    return base


def supervise(
    result: Dict[str, Any],
    query: str,
    user: str,
    bot_name: Optional[str],
    complexity: str = "simple",
) -> Dict[str, Any]:
    """Post-dispatch supervision.  Reflection-revises NL responses, attaches
    telemetry to the response payload.  Never raises."""
    if not isinstance(result, dict):
        return result
    if not is_enabled():
        return result

    intel = _get_layer(user)
    if intel is None:
        return result

    answer = result.get("response")
    if not isinstance(answer, str) or not answer.strip():
        # Nothing to refine; just attach minimal telemetry.
        result.setdefault("supervisor", {})
        result["supervisor"].update({"complexity": complexity, "applied": []})
        return result

    applied = []
    autonomy = _autonomy_from_query(query)

    # Reflection only on natural-language bots, when autonomy >= command, and
    # only when the request was non-trivial.  We bound to 1 critic iteration
    # to keep latency predictable.
    eligible = (bot_name in _NL_BOTS or bot_name in (None, "", "sales_order_bot")) and (
        autonomy in ("command", "agent") and complexity != "simple"
    )
    if eligible:
        try:
            refined = intel.refine(
                query=query,
                draft=answer,
                criteria=[
                    "Every ERPNext document ID mentioned must come from the "
                    "supplied context — never invent IDs.",
                    "Do not fabricate totals, dates or status values.",
                    "If the action is destructive, surface required confirmations.",
                ],
                max_iterations=1,
            )
            if refined and refined.final_answer and refined.final_answer.strip():
                result["response"] = refined.final_answer
                applied.append("reflection")
            # Bug Reporter: critic rejected the answer (likely hallucination).
            if refined and not refined.accepted:
                try:
                    from raven_ai_agent.bug_reporter import capture as _capture_bug
                    _capture_bug(
                        severity="Medium",
                        bot=bot_name,
                        intent=bot_name,
                        user=user,
                        query=query,
                        failure_class="reflection_rejected",
                        result_text=(refined.final_answer or "")[:1500],
                        supervisor_meta={
                            "complexity": complexity,
                            "iterations": refined.iterations,
                        },
                    )
                except Exception:
                    pass
        except Exception as exc:  # noqa: BLE001
            frappe.logger().debug(f"[AgentSupervisor] reflection failed: {exc}")

    result.setdefault("supervisor", {})
    result["supervisor"].update(
        {
            "complexity": complexity,
            "applied": applied,
            "bot": bot_name,
        }
    )
    return result


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------
def _get_layer(user: str):
    """Build an IntelligenceLayer using V2's provider + memory retriever, but
    do NOT instantiate V2 itself — supervisor must work for every bot, not
    just the V1 fallback path."""
    if not _PATTERNS_AVAILABLE:
        return None
    try:
        from raven_ai_agent.providers import get_provider

        settings = (
            frappe.get_single("AI Agent Settings").as_dict()
            if frappe.db.exists("DocType", "AI Agent Settings")
            else {}
        )
        provider_name = settings.get("default_provider", "openai")
        provider = get_provider(provider_name, settings)
        return IntelligenceLayer(
            provider=provider,
            retriever=_make_memory_retriever(user),
            secondary_providers=_collect_secondary_providers(provider_name, settings),
        )
    except Exception as exc:  # noqa: BLE001
        frappe.logger().debug(f"[AgentSupervisor] cannot build layer: {exc}")
        return None


def _make_memory_retriever(user: str):
    """Bridge RAGRetriever -> MemoryMixin.search_memories."""
    def _retrieve(query: str, k: int = 5):
        try:
            from raven_ai_agent.api.agent import RaymondLucyAgent

            agent = RaymondLucyAgent(user)
            hits = agent.search_memories(query, limit=k) or []
            out = []
            for h in hits:
                if not isinstance(h, dict):
                    continue
                out.append(
                    {
                        "content": h.get("content", ""),
                        "source": h.get("source") or h.get("name") or "AI Memory",
                        "score": (
                            h.get("importance_score")
                            or h.get("similarity")
                            or 0.0
                        ),
                    }
                )
            return out
        except Exception as exc:  # noqa: BLE001
            frappe.logger().debug(f"[AgentSupervisor] memory retriever: {exc}")
            return []

    return _retrieve


def _collect_secondary_providers(primary_name: str, settings: Dict) -> Dict:
    out: Dict[str, Any] = {}
    for name in ("openai", "deepseek", "claude", "minimax", "ollama"):
        if name == primary_name:
            continue
        try:
            from raven_ai_agent.providers import get_provider

            out[name] = get_provider(name, settings)
        except Exception:  # noqa: BLE001
            continue
    return out


# --- query introspection helpers (best-effort, never raise) ---------------- #
def _autonomy_from_query(query: str) -> str:
    q = f" {(query or '').lower().strip()} "
    if q.lstrip().startswith("!") or " !" in q:
        # Karpathy convention: ! prefix = direct execution
        return "command"
    for kw in ("submit", "cancel", "delete", "execute"):
        if f" {kw} " in q:
            return "command"
    return "copilot"


def _action_kind(bot_name: Optional[str], query: str) -> str:
    q = (query or "").lower()
    if "submit" in q:
        return "submit"
    if "payment" in q or bot_name == "payment_bot":
        return "payment"
    if "convert" in q:
        return "convert"
    if any(k in q for k in (" all ", " every ", "bulk")):
        return "bulk"
    if bot_name in _MUTATING_BOTS:
        return "update"
    return "read"


def _guess_doctype(query: str) -> Optional[str]:
    q = (query or "")
    for doctype in (
        "Sales Invoice",
        "Sales Order",
        "Purchase Order",
        "Quotation",
        "Work Order",
        "Payment Entry",
        "Delivery Note",
    ):
        if doctype.lower() in q.lower():
            return doctype
    return None


def _guess_doc_name(query: str) -> Optional[str]:
    import re

    m = re.search(
        r"\b(SAL-QTN|SO|MFG-WO|ACC-SINV|SINV|ACC-PAY|PE|DN|PO|MAT-MR)-[\w\-/]+",
        query or "",
    )
    return m.group(0) if m else None


def _guess_bulk_count(query: str) -> int:
    import re

    m = re.search(r"\b(\d{2,5})\s+(documents|invoices|orders|items)\b", query or "")
    return int(m.group(1)) if m else 0
