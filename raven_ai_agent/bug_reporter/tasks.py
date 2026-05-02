"""
Async worker entry points for the bug reporter.

Invoked via ``frappe.enqueue("raven_ai_agent.bug_reporter.tasks.publish_bug", ...)``
from ``collector.capture()``.  Runs in the short queue with
``enqueue_after_commit=True``.

Responsibilities (in order):
  1. Upsert ``Raven Agent Bug`` keyed by fingerprint.
  2. Within dedup window: bump occurrence count + append child snippet.
  3. Outside dedup window (or first occurrence): create HD Ticket / Issue,
     create GitHub issue, cross-link both, save URLs back on the doc.
  4. If ``occurrence_count >= autopause_threshold`` and auto-pause enabled,
     pause autonomy for the bot/user and start the escalation timer.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import frappe

from .destinations.helpdesk import publish as publish_helpdesk
from .destinations.github import publish as publish_github


_DEDUP_WINDOW_HOURS_DEFAULT = 24
_AUTOPAUSE_THRESHOLD_DEFAULT = 5
_AUTOPAUSE_WINDOW_MINUTES_DEFAULT = 60


def _config(key: str, fallback):
    """Read tunables from AI Agent Settings, then site_config, then fallback."""
    try:
        v = frappe.db.get_single_value("AI Agent Settings", key)
        if v not in (None, ""):
            return v
    except Exception:  # noqa: BLE001
        pass
    try:
        v = (frappe.conf or {}).get(key)
        if v not in (None, ""):
            return v
    except Exception:  # noqa: BLE001
        pass
    return fallback


def publish_bug(payload: Dict[str, Any]) -> None:
    """Top-level entry point.  Wrapped in try/except so a worker failure
    never escalates beyond the worker."""
    try:
        _do_publish(payload)
    except Exception as exc:  # noqa: BLE001
        frappe.logger().exception(f"[bug_reporter] publish_bug failed: {exc}")
        # As a last resort, drop a marker into the standard Error Log.
        try:
            frappe.log_error(
                title=f"[Raven Bug Reporter] worker failed for fp={payload.get('fp')}",
                message=str(exc),
            )
        except Exception:  # noqa: BLE001
            pass


# ---- internals ----------------------------------------------------------- #
def _do_publish(payload: Dict[str, Any]) -> None:
    fp = payload.get("fp")
    if not fp:
        return
    if not _doctype_exists("Raven Agent Bug"):
        # Fixtures haven't been migrated yet — Error Log already has it.
        frappe.logger().info("[bug_reporter] Raven Agent Bug doctype missing; skipping upsert")
        return

    bug, dedup_hit = _upsert_bug(payload)
    if not bug:
        return

    if dedup_hit:
        return  # we already filed external destinations for this fp

    # First (or out-of-window) occurrence: file external destinations.
    helpdesk_url: Optional[str] = None
    github_url: Optional[str] = None
    try:
        github_url = publish_github(payload)
    except Exception as exc:  # noqa: BLE001
        frappe.logger().warning(f"[bug_reporter] github publish failed: {exc}")
    try:
        helpdesk_url = publish_helpdesk(payload, cross_link_url=github_url)
    except Exception as exc:  # noqa: BLE001
        frappe.logger().warning(f"[bug_reporter] helpdesk publish failed: {exc}")

    # Save back URLs.
    try:
        bug.db_set("helpdesk_url", helpdesk_url or "", update_modified=False)
        bug.db_set("github_url", github_url or "", update_modified=False)
        frappe.db.commit()
    except Exception as exc:  # noqa: BLE001
        frappe.logger().warning(f"[bug_reporter] save destination urls failed: {exc}")

    # Auto-pause check.
    _maybe_autopause(bug)


def _upsert_bug(payload: Dict[str, Any]):
    """Return (bug_doc, deduped) tuple.  When deduped is True, the existing
    bug had an occurrence within the dedup window and we should NOT re-publish
    to external destinations."""
    fp = payload["fp"]
    dedup_hours = int(_config("bug_reporter_dedup_window_hours",
                              _DEDUP_WINDOW_HOURS_DEFAULT))

    name = frappe.db.exists("Raven Agent Bug", {"fingerprint": fp})
    if name:
        bug = frappe.get_doc("Raven Agent Bug", name)
        last = bug.get("last_seen_at")
        deduped = False
        if last:
            try:
                last_dt = frappe.utils.get_datetime(last)
                if datetime.now() - last_dt < timedelta(hours=dedup_hours):
                    deduped = True
            except Exception:  # noqa: BLE001
                pass

        bug.append("occurrences", _occurrence_row(payload))
        bug.occurrence_count = int(bug.occurrence_count or 0) + 1
        bug.last_seen_at = frappe.utils.now()
        # If we crossed a severity boundary upward, escalate.
        if _severity_rank(payload.get("severity")) > _severity_rank(bug.severity):
            bug.severity = payload.get("severity")
        bug.save(ignore_permissions=True)
        frappe.db.commit()
        return bug, deduped

    # First time we see this fingerprint.
    bug = frappe.get_doc({
        "doctype": "Raven Agent Bug",
        "fingerprint": fp,
        "severity": payload.get("severity") or "Medium",
        "environment": payload.get("env"),
        "app": payload.get("app"),
        "bot": payload.get("bot"),
        "intent": payload.get("intent"),
        "failure_class": payload.get("failure_class"),
        "first_seen_at": frappe.utils.now(),
        "last_seen_at": frappe.utils.now(),
        "occurrence_count": 1,
        "summary": _summary(payload),
        "occurrences": [_occurrence_row(payload)],
    })
    bug.insert(ignore_permissions=True)
    frappe.db.commit()
    return bug, False


def _summary(payload: Dict[str, Any]) -> str:
    exc = payload.get("exception") or {}
    if exc.get("type"):
        return f"{exc.get('type')}: {(exc.get('message') or '')[:200]}"
    return f"{payload.get('failure_class')}: {(payload.get('result_text') or '')[:200]}"


def _occurrence_row(payload: Dict[str, Any]) -> Dict[str, Any]:
    exc = payload.get("exception") or {}
    return {
        "doctype": "Raven Agent Bug Occurrence",
        "occurred_at": frappe.utils.now(),
        "user": payload.get("user"),
        "environment": payload.get("env"),
        "query_excerpt": (payload.get("query") or "")[:1000],
        "exception_type": exc.get("type") or "",
        "exception_message": (exc.get("message") or "")[:500],
    }


def _severity_rank(s: Optional[str]) -> int:
    return {"Low": 1, "Medium": 2, "High": 3}.get((s or "Medium"), 2)


# ---- auto-pause + escalation -------------------------------------------- #
def _maybe_autopause(bug) -> None:
    """When a bot accumulates many High bugs in a window, downgrade its
    autonomy to Copilot.  The escalation timer (separate scheduled job)
    chases the operator if no human acks within configured thresholds."""
    if not _truthy(_config("bug_reporter_autopause_enabled", 1)):
        return
    if (bug.severity or "").lower() != "high":
        return

    threshold = int(_config("bug_reporter_autopause_threshold",
                            _AUTOPAUSE_THRESHOLD_DEFAULT))
    window_minutes = int(_config("bug_reporter_autopause_window_minutes",
                                 _AUTOPAUSE_WINDOW_MINUTES_DEFAULT))

    # Count High-severity bugs for this bot in the window.
    cutoff = frappe.utils.add_to_date(frappe.utils.now(), minutes=-window_minutes)
    try:
        recent = frappe.db.count(
            "Raven Agent Bug",
            filters={
                "bot": bug.bot,
                "severity": "High",
                "last_seen_at": [">", cutoff],
            },
        )
    except Exception:  # noqa: BLE001
        recent = 0

    if recent >= threshold and not bug.autonomy_paused:
        bug.db_set("autonomy_paused", 1, update_modified=False)
        bug.db_set("autonomy_paused_at", frappe.utils.now(), update_modified=False)
        frappe.db.commit()
        frappe.logger().warning(
            f"[bug_reporter] autonomy paused for bot={bug.bot} "
            f"after {recent} High bugs in {window_minutes}m"
        )


def _doctype_exists(name: str) -> bool:
    try:
        return bool(frappe.db.exists("DocType", name))
    except Exception:  # noqa: BLE001
        return False


def _truthy(v) -> bool:
    if v in (1, True):
        return True
    if isinstance(v, str):
        return v.strip().lower() in {"1", "true", "yes", "on"}
    return False


# ---- escalation timer (called by scheduler) ----------------------------- #
def run_escalation_timer() -> None:
    """Scheduler entry point — runs every 5 minutes via hooks.py.

    Looks at every paused bug, compares paused_at against alarm thresholds,
    and emits notifications when a threshold is crossed (and not yet
    acknowledged at that level).
    """
    if not _doctype_exists("Raven Agent Bug"):
        return

    a1 = int(_config("bug_reporter_escalation_alarm1_minutes", 15))
    a2 = int(_config("bug_reporter_escalation_alarm2_minutes", 30))
    a3 = int(_config("bug_reporter_escalation_alarm3_minutes", 45))
    now = frappe.utils.now_datetime()

    paused = frappe.get_all(
        "Raven Agent Bug",
        filters={"autonomy_paused": 1},
        fields=["name", "bot", "severity", "autonomy_paused_at",
                "alarm1_sent", "alarm2_sent", "alarm3_sent",
                "helpdesk_url", "github_url", "fingerprint"],
        limit=200,
    )

    for row in paused:
        paused_at = frappe.utils.get_datetime(row["autonomy_paused_at"])
        elapsed_min = int((now - paused_at).total_seconds() / 60)

        if elapsed_min >= a3 and not row["alarm3_sent"]:
            _emit_alarm(row, level=3)
            frappe.db.set_value("Raven Agent Bug", row["name"], "alarm3_sent", 1)
        elif elapsed_min >= a2 and not row["alarm2_sent"]:
            _emit_alarm(row, level=2)
            frappe.db.set_value("Raven Agent Bug", row["name"], "alarm2_sent", 1)
        elif elapsed_min >= a1 and not row["alarm1_sent"]:
            _emit_alarm(row, level=1)
            frappe.db.set_value("Raven Agent Bug", row["name"], "alarm1_sent", 1)

    frappe.db.commit()


def _emit_alarm(row: Dict[str, Any], *, level: int) -> None:
    """Send the configured notification for an alarm level.  Uses Raven
    DM + email by default; fully best-effort."""
    subject = (
        f"[ALARM-{level}] Raven bug {row['fingerprint']} on bot {row['bot']} "
        f"unacknowledged"
    )
    body = (
        f"Severity: {row.get('severity')}\n"
        f"HD Ticket: {row.get('helpdesk_url') or '(none)'}\n"
        f"GitHub:    {row.get('github_url') or '(none)'}\n"
        f"Open the Raven Agent Bug record to acknowledge."
    )
    # 1. Email — only if user list is configured.
    users = _alarm_users(level)
    if users:
        try:
            frappe.sendmail(
                recipients=users,
                subject=subject,
                message=body,
                now=False,
            )
        except Exception as exc:  # noqa: BLE001
            frappe.logger().warning(f"[bug_reporter] alarm email failed: {exc}")

    # 2. Always log to Error Log so it surfaces in Log Settings dashboards.
    try:
        frappe.log_error(title=subject[:140], message=body)
    except Exception:  # noqa: BLE001
        pass


def _alarm_users(level: int) -> list[str]:
    """List of user emails for a given alarm level.  Stored as comma-separated
    on AI Agent Settings: bug_reporter_alarm{1,2,3}_users."""
    field = f"bug_reporter_alarm{level}_users"
    raw = _config(field, "") or ""
    return [u.strip() for u in str(raw).split(",") if u.strip()]
