"""
Guardrails / Safety Pattern (Chapter 18)
========================================

Static + LLM-as-judge checks that run BEFORE Raven mutates ERPNext.
Designed to compose with the existing autonomy slider:
  COPILOT → suggest only         (no mutation, ignore guardrails)
  COMMAND → require human ack    (run guardrails; show violations to user)
  AGENT   → execute autonomously (block on any High violation)

Pre-built rules cover the most common Raven footguns:
  * "!submit" without a recognised doctype/name pair
  * Payment Entry with mismatched currency / amount
  * Quotation→SO conversion when CRITICAL_FIELDS would diverge
  * Bulk operations on >N documents without explicit confirmation
You can register additional rules with `Guardrails.register(rule_fn)`.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class Severity(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


@dataclass
class GuardrailViolation:
    rule: str
    severity: Severity
    message: str
    suggestion: str = ""


@dataclass
class GuardrailReport:
    violations: List[GuardrailViolation] = field(default_factory=list)

    @property
    def has_high(self) -> bool:
        return any(v.severity == Severity.HIGH for v in self.violations)

    @property
    def passed(self) -> bool:
        return not self.violations

    def format(self) -> str:
        if self.passed:
            return "Guardrails: ✅ all checks passed"
        lines = ["Guardrails report:"]
        for v in self.violations:
            tag = {"Low": "ℹ️", "Medium": "⚠️", "High": "⛔"}.get(v.severity.value, "•")
            lines.append(f"  {tag} [{v.severity.value}] {v.rule}: {v.message}")
            if v.suggestion:
                lines.append(f"      → suggestion: {v.suggestion}")
        return "\n".join(lines)


# Rule signature: fn(action: dict) -> Optional[GuardrailViolation]
Rule = Callable[[Dict[str, Any]], Optional[GuardrailViolation]]


class Guardrails:
    """A small pluggable rulebook applied to a proposed agent action.

    `action` is a free-form dict describing what the agent intends to do.
    Recommended keys:
        kind        - "submit" | "create" | "convert" | "bulk" | "payment" | ...
        doctype     - ERPNext doctype, e.g. "Sales Invoice"
        name        - ERPNext document name when known
        params      - dict of arguments
        autonomy    - "copilot" | "command" | "agent"
        bulk_count  - int, when applicable
    """

    def __init__(self, rules: Optional[List[Rule]] = None):
        self.rules: List[Rule] = list(rules or DEFAULT_RULES)

    def register(self, rule: Rule) -> None:
        self.rules.append(rule)

    def check(self, action: Dict[str, Any]) -> GuardrailReport:
        report = GuardrailReport()
        for rule in self.rules:
            try:
                v = rule(action)
            except Exception as exc:  # never let a rule crash the agent
                logger.warning("Guardrail rule %s errored: %s", rule.__name__, exc)
                continue
            if v is not None:
                report.violations.append(v)
        return report

    def enforce(self, action: Dict[str, Any]) -> GuardrailReport:
        """Same as check(), but raises if any HIGH violation is found and
        the action's autonomy is 'agent'."""
        report = self.check(action)
        if report.has_high and action.get("autonomy") == "agent":
            raise GuardrailBlocked(report)
        return report


class GuardrailBlocked(RuntimeError):
    def __init__(self, report: GuardrailReport):
        super().__init__(report.format())
        self.report = report


# ---------------------------------------------------------------------------
# Default rules (Raven-specific)
# ---------------------------------------------------------------------------
_SUBMIT_KINDS = {"submit", "submit_doc"}
_BULK_THRESHOLD = 25
_MUTATING_KINDS = {"submit", "create", "convert", "payment", "delete", "update", "bulk"}


def rule_submit_requires_target(action: Dict[str, Any]) -> Optional[GuardrailViolation]:
    if action.get("kind") not in _SUBMIT_KINDS:
        return None
    if not action.get("doctype") or not action.get("name"):
        return GuardrailViolation(
            rule="submit_requires_target",
            severity=Severity.HIGH,
            message="Submit requested without an explicit doctype + document name.",
            suggestion="Resolve the document first via doc_resolver, then retry.",
        )
    return None


def rule_payment_currency_match(action: Dict[str, Any]) -> Optional[GuardrailViolation]:
    if action.get("kind") != "payment":
        return None
    params = action.get("params") or {}
    si_currency = params.get("invoice_currency")
    pe_currency = params.get("payment_currency")
    if si_currency and pe_currency and si_currency != pe_currency:
        return GuardrailViolation(
            rule="payment_currency_match",
            severity=Severity.HIGH,
            message=(
                f"Payment currency {pe_currency} ≠ invoice currency {si_currency}."
            ),
            suggestion="Set custom_customer_invoice_currency or convert the amount.",
        )
    return None


def rule_quotation_so_field_match(
    action: Dict[str, Any],
) -> Optional[GuardrailViolation]:
    if action.get("kind") != "convert":
        return None
    params = action.get("params") or {}
    diffs = params.get("critical_field_diffs") or []
    if diffs:
        return GuardrailViolation(
            rule="quotation_so_field_match",
            severity=Severity.HIGH,
            message=(
                "Quotation→SO conversion would diverge on CRITICAL_FIELDS: "
                + ", ".join(diffs)
            ),
            suggestion="Reconcile the source quotation first (truth_hierarchy).",
        )
    return None


def rule_bulk_requires_ack(action: Dict[str, Any]) -> Optional[GuardrailViolation]:
    count = int(action.get("bulk_count") or 0)
    if count >= _BULK_THRESHOLD and not action.get("user_ack"):
        return GuardrailViolation(
            rule="bulk_requires_ack",
            severity=Severity.MEDIUM,
            message=f"Bulk operation on {count} docs without explicit confirmation.",
            suggestion="Re-issue the command with !confirm or set autonomy=command.",
        )
    return None


def rule_copilot_blocks_mutation(
    action: Dict[str, Any],
) -> Optional[GuardrailViolation]:
    if action.get("autonomy") != "copilot":
        return None
    if action.get("kind") in _MUTATING_KINDS:
        return GuardrailViolation(
            rule="copilot_blocks_mutation",
            severity=Severity.HIGH,
            message="COPILOT mode cannot mutate ERPNext data.",
            suggestion="Raise autonomy to COMMAND or AGENT to perform this action.",
        )
    return None


DEFAULT_RULES: List[Rule] = [
    rule_submit_requires_target,
    rule_payment_currency_match,
    rule_quotation_so_field_match,
    rule_bulk_requires_ack,
    rule_copilot_blocks_mutation,
]
