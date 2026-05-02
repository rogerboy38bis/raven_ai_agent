"""
Bug Reporter — synchronous capture entry point.

Public surface: ``capture(...)``.  Always cheap.  Logs to ``frappe.log_error``
synchronously (the request is already in trouble, this is on the failure
path).  Then enqueues an async worker job for the rest (HD Ticket / GitHub).

Never raises — this code runs from inside ``except`` blocks.
"""
from __future__ import annotations

import os
import sys
import traceback
from typing import Any, Dict, Optional

import frappe

from .fingerprint import fingerprint
from .redactor import redact, redact_dict


# ---- enable / config ----------------------------------------------------- #
def is_enabled() -> bool:
    """True when the bug reporter should run for this request."""
    flag = os.environ.get("RAVEN_BUG_REPORTER", "").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return False
    if flag in {"1", "true", "yes", "on"}:
        return True
    # Per-site fallback (default ON when AI Agent Settings flag is set)
    try:
        return bool(
            frappe.db.get_single_value("AI Agent Settings", "bug_reporter_enabled")
        )
    except Exception:  # noqa: BLE001
        return False


def _environment_label() -> str:
    """Short label used to tag bugs by environment (A2 strategy).

    Resolution: env var > site_config > heuristic.
    """
    label = os.environ.get("RAVEN_ENV") or ""
    if not label:
        try:
            label = (frappe.conf or {}).get("bug_reporter_environment") or ""
        except Exception:  # noqa: BLE001
            label = ""
    if not label:
        # Heuristic: if /.dockerenv present, assume container; otherwise direct bench.
        try:
            if os.path.exists("/.dockerenv"):
                label = "test"  # most Docker setups in this fleet are test/prod
            else:
                label = "server-sandbox"
        except Exception:  # noqa: BLE001
            label = "unknown"
    return str(label).strip().lower() or "unknown"


def _detect_app_from_module(module: Optional[str], path: Optional[str]) -> str:
    """Pick the app name from a Python module path or file path."""
    if module:
        for app in (
            "raven_ai_agent", "amb_w_spc", "amb_w_tds", "amb_print",
            "raven", "erpnext", "frappe",
        ):
            if module.startswith(app + ".") or module == app:
                return app
    if path:
        for app in (
            "raven_ai_agent", "amb_w_spc", "amb_w_tds", "amb_print",
            "raven", "erpnext", "frappe",
        ):
            if f"/apps/{app}/" in path:
                return app
    return "raven_ai_agent"


def _exception_meta(exc: BaseException) -> Dict[str, Any]:
    tb = traceback.format_exc()
    last = exc.__traceback__
    while last and last.tb_next:
        last = last.tb_next
    file_path = last.tb_frame.f_code.co_filename if last else ""
    module = last.tb_frame.f_globals.get("__name__", "") if last else ""
    return {
        "type": exc.__class__.__name__,
        "module": module,
        "message": str(exc),
        "traceback": tb,
        "file": file_path,
        "line": last.tb_lineno if last else 0,
    }


# ---- public API ---------------------------------------------------------- #
def capture(
    *,
    severity: str = "Medium",
    bot: Optional[str] = None,
    intent: Optional[str] = None,
    user: Optional[str] = None,
    query: Optional[str] = None,
    exception: Optional[BaseException] = None,
    failure_class: str = "exception",
    result_text: Optional[str] = None,
    expected: Optional[str] = None,
    supervisor_meta: Optional[Dict] = None,
    extra: Optional[Dict] = None,
) -> Optional[str]:
    """Record a bug.  Returns the fingerprint, or None when the reporter
    is disabled / fails.  Never raises.
    """
    if not is_enabled():
        return None

    try:
        env = _environment_label()
        exc_meta: Dict[str, Any] = {}
        if exception is not None:
            exc_meta = _exception_meta(exception)

        app = _detect_app_from_module(exc_meta.get("module"), exc_meta.get("file"))

        # Compose error_summary used for dedup.
        if exc_meta:
            error_summary = f"{exc_meta.get('type')}: {exc_meta.get('message')}"
        elif failure_class == "guardrail_block":
            error_summary = "guardrails high violation"
        elif failure_class == "reflection_rejected":
            error_summary = "reflection rejected after max iterations"
        elif failure_class == "result_failure":
            error_summary = (result_text or "")[:200]
        elif failure_class == "provider_chain_exhausted":
            error_summary = "all llm providers failed"
        else:
            error_summary = result_text or "unknown failure"

        fp = fingerprint(
            bot=bot,
            intent=intent,
            exception_type=exc_meta.get("type"),
            exception_module=exc_meta.get("module"),
            error_summary=error_summary,
            failure_class=failure_class,
        )

        # ALWAYS log to the standard Frappe Error Log first.  Cheap and
        # gives us a stable system-wide audit trail even if HD Ticket /
        # GitHub destinations are misconfigured.
        title = f"[Raven Bug:{severity}:{fp}:{env}] {bot or '?'}/{intent or '?'} — {error_summary[:80]}"
        try:
            frappe.log_error(
                title=title[:140],
                message=_format_error_log_body(
                    fp=fp, env=env, app=app, severity=severity,
                    bot=bot, intent=intent, user=user, query=query,
                    failure_class=failure_class, exc=exc_meta,
                    result_text=result_text, supervisor_meta=supervisor_meta,
                    extra=extra,
                )[:9500],
                reference_doctype="Raven Agent Bug",
                reference_name=fp,
            )
        except Exception as log_exc:  # noqa: BLE001
            # Last-resort: stderr.  Never crash the agent.
            print(f"[bug_reporter] frappe.log_error failed: {log_exc}", file=sys.stderr)

        # Enqueue async workers (HD Ticket + GitHub + Raven Agent Bug doctype).
        # enqueue_after_commit so we don't fire jobs for transactions that get
        # rolled back.  job_name dedups identical retries within the same tick.
        try:
            payload = _build_payload(
                fp=fp, env=env, app=app, severity=severity,
                bot=bot, intent=intent, user=user, query=query,
                failure_class=failure_class, exc=exc_meta,
                result_text=result_text, expected=expected,
                supervisor_meta=supervisor_meta, extra=extra,
            )
            frappe.enqueue(
                "raven_ai_agent.bug_reporter.tasks.publish_bug",
                queue="short",
                job_name=f"bug_reporter:{fp}",
                enqueue_after_commit=True,
                payload=payload,
            )
        except Exception as enqueue_exc:  # noqa: BLE001
            print(f"[bug_reporter] enqueue failed: {enqueue_exc}", file=sys.stderr)

        return fp
    except Exception as outer_exc:  # noqa: BLE001
        # The reporter itself must never break the agent.
        print(f"[bug_reporter] capture failed: {outer_exc}", file=sys.stderr)
        return None


# ---- payload helpers ----------------------------------------------------- #
def _redact_pii_for_github() -> bool:
    """Default: keep PII because rogerboy38bis is private.  Override per site."""
    try:
        v = frappe.db.get_single_value("AI Agent Settings", "bug_reporter_redact_pii_on_github")
        return bool(v) if v is not None else False
    except Exception:  # noqa: BLE001
        return False


def _build_payload(**kw) -> Dict[str, Any]:
    """Build the dict that the async worker receives.  Apply secret redaction
    here so we never persist or transmit secrets, even to local Error Log."""
    redacted_query = redact(kw.get("query") or "")
    redacted_result = redact(kw.get("result_text") or "")
    redacted_extra = redact_dict(kw.get("extra") or {})
    redacted_sup = redact_dict(kw.get("supervisor_meta") or {})
    exc = kw.get("exc") or {}
    redacted_tb = redact(exc.get("traceback") or "")

    return {
        "fp": kw["fp"],
        "env": kw["env"],
        "app": kw["app"],
        "severity": kw["severity"],
        "bot": kw["bot"],
        "intent": kw["intent"],
        "user": kw["user"],
        "query": redacted_query,
        "failure_class": kw["failure_class"],
        "exception": {
            "type": exc.get("type"),
            "module": exc.get("module"),
            "message": redact(exc.get("message") or ""),
            "traceback": redacted_tb,
            "file": exc.get("file"),
            "line": exc.get("line"),
        },
        "result_text": redacted_result,
        "expected": redact(kw.get("expected") or ""),
        "supervisor_meta": redacted_sup,
        "extra": redacted_extra,
    }


def _format_error_log_body(**kw) -> str:
    exc = kw.get("exc") or {}
    parts = [
        f"Bug fingerprint: {kw['fp']}",
        f"Environment:     {kw['env']}",
        f"App:             {kw['app']}",
        f"Severity:        {kw['severity']}",
        f"Bot/Intent:      {kw.get('bot') or '?'} / {kw.get('intent') or '?'}",
        f"User:            {kw.get('user') or '?'}",
        f"Failure class:   {kw['failure_class']}",
        "",
        "Query (redacted):",
        redact(kw.get("query") or "")[:1500],
        "",
    ]
    if exc:
        parts += [
            f"Exception: {exc.get('type')} ({exc.get('module')}) at {exc.get('file')}:{exc.get('line')}",
            f"Message:   {redact(exc.get('message') or '')}",
            "",
            "Traceback (redacted):",
            redact(exc.get("traceback") or "")[:4000],
            "",
        ]
    if kw.get("result_text"):
        parts += ["Result text (redacted):", redact(kw["result_text"])[:1500], ""]
    if kw.get("supervisor_meta"):
        parts += ["Supervisor meta:", str(redact_dict(kw["supervisor_meta"]))[:1500], ""]
    if kw.get("extra"):
        parts += ["Extra:", str(redact_dict(kw["extra"]))[:1500], ""]
    return "\n".join(parts)
