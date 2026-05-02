"""
Help Desk destination — auto-detect three-tier:
  1. HD Ticket   (when frappe/helpdesk app installed)
  2. Issue       (Frappe core fallback when 'Issue' doctype is available)
  3. None        (Error Log already captured everything; do nothing)
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import frappe


def _doctype_exists(name: str) -> bool:
    try:
        return bool(frappe.db.exists("DocType", name))
    except Exception:  # noqa: BLE001
        return False


def _format_html(payload: Dict[str, Any], cross_link_url: Optional[str]) -> str:
    """Build the HTML body for the helpdesk ticket / issue."""
    exc = payload.get("exception") or {}
    parts = []

    if cross_link_url:
        parts.append(
            f'<p><strong>GitHub:</strong> '
            f'<a href="{cross_link_url}" target="_blank" rel="noopener">'
            f'{cross_link_url}</a></p>'
        )

    parts.append("<table border='0' cellpadding='4'>")
    rows = [
        ("Fingerprint", payload.get("fp")),
        ("Environment", payload.get("env")),
        ("App", payload.get("app")),
        ("Severity", payload.get("severity")),
        ("Bot", payload.get("bot")),
        ("Intent", payload.get("intent")),
        ("User", payload.get("user")),
        ("Failure class", payload.get("failure_class")),
    ]
    for label, value in rows:
        parts.append(
            f"<tr><td><strong>{label}</strong></td><td>{frappe.utils.escape_html(str(value or '?'))}</td></tr>"
        )
    parts.append("</table>")

    parts.append("<h4>Query</h4>")
    parts.append(f"<pre>{frappe.utils.escape_html((payload.get('query') or '')[:2000])}</pre>")

    if exc.get("type"):
        parts.append(
            f"<h4>Exception: {frappe.utils.escape_html(exc['type'])} "
            f"<small>({frappe.utils.escape_html(str(exc.get('module') or ''))})</small></h4>"
        )
        parts.append(
            f"<p>{frappe.utils.escape_html(str(exc.get('message') or ''))}</p>"
        )
        parts.append("<h4>Traceback</h4>")
        parts.append(f"<pre>{frappe.utils.escape_html((exc.get('traceback') or '')[:6000])}</pre>")

    if payload.get("result_text"):
        parts.append("<h4>Result Text</h4>")
        parts.append(
            f"<pre>{frappe.utils.escape_html((payload['result_text'])[:2000])}</pre>"
        )

    if payload.get("supervisor_meta"):
        parts.append("<h4>Supervisor Telemetry</h4>")
        parts.append(
            f"<pre>{frappe.utils.escape_html(str(payload['supervisor_meta'])[:1500])}</pre>"
        )

    if payload.get("extra"):
        parts.append("<h4>Extra</h4>")
        parts.append(f"<pre>{frappe.utils.escape_html(str(payload['extra'])[:1500])}</pre>")

    return "\n".join(parts)


def publish(payload: Dict[str, Any], cross_link_url: Optional[str] = None) -> Optional[str]:
    """Create an HD Ticket or Issue.  Returns the doc URL or None.

    Best-effort.  Caller wraps in try/except.
    """
    subject = (
        f"[{payload.get('env')}][bug:{payload.get('fp')}] "
        f"{payload.get('bot') or '?'}/{payload.get('intent') or '?'} "
        f"— {(payload.get('exception', {}).get('type') or payload.get('failure_class') or 'failure')}"
    )[:140]

    body = _format_html(payload, cross_link_url=cross_link_url)

    # Tier 1: HD Ticket (Help Desk app)
    if _doctype_exists("HD Ticket"):
        try:
            doc = frappe.get_doc({
                "doctype": "HD Ticket",
                "subject": subject,
                "description": body,
                "via_customer_portal": 0,
                "status": "Open" if _doctype_exists("HD Ticket Status") else None,
            }).insert(ignore_permissions=True)
            return _site_url("HD Ticket", doc.name)
        except Exception as exc:  # noqa: BLE001
            frappe.logger().warning(f"[bug_reporter] HD Ticket create failed: {exc}")

    # Tier 2: built-in Issue
    if _doctype_exists("Issue"):
        try:
            doc = frappe.get_doc({
                "doctype": "Issue",
                "subject": subject,
                "description": body,
                "raised_by": payload.get("user") or "Administrator",
                "priority": _issue_priority(payload.get("severity")),
            }).insert(ignore_permissions=True)
            return _site_url("Issue", doc.name)
        except Exception as exc:  # noqa: BLE001
            frappe.logger().warning(f"[bug_reporter] Issue create failed: {exc}")

    # Tier 3: nothing — Error Log already has everything.
    return None


def _issue_priority(severity: Optional[str]) -> str:
    return {"High": "High", "Medium": "Medium", "Low": "Low"}.get(severity or "Medium", "Medium")


def _site_url(doctype: str, name: str) -> str:
    try:
        host = frappe.utils.get_url()
    except Exception:  # noqa: BLE001
        host = ""
    return f"{host}/app/{doctype.lower().replace(' ', '-')}/{name}"
