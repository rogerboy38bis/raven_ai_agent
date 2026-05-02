"""
Raven Agent Bug Reporter
========================

Publish bugs from any agent failure to:
  1. Frappe Error Log         (always)
  2. Help Desk HD Ticket / Issue (auto-detect three-tier graceful degradation)
  3. GitHub issue on the per-app rogerboy38bis fork

All async work runs in a worker via ``frappe.enqueue`` with
``enqueue_after_commit=True`` so we never block the chat request.

See ``docs/AGENT_BUG_REPORTER.md`` for the full design.
"""

from .collector import capture, is_enabled
from .fingerprint import fingerprint
from .redactor import redact, redact_dict, redact_secrets, redact_pii

__all__ = [
    "capture",
    "is_enabled",
    "fingerprint",
    "redact",
    "redact_dict",
    "redact_secrets",
    "redact_pii",
]
