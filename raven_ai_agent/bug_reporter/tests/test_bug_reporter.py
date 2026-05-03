"""
Smoke tests for the bug reporter (no Frappe runtime needed).

Run with:
    cd ~/frappe-bench/apps/raven_ai_agent
    PYTHONPATH=. python3 raven_ai_agent/bug_reporter/tests/test_bug_reporter.py
"""
from __future__ import annotations

import os
import sys
import types


def _install_stubs():
    if "frappe" not in sys.modules:
        fake = types.ModuleType("frappe")
        fake.conf = {}
        fake.flags = types.SimpleNamespace()

        def _whitelist(*dargs, **dkw):
            def _wrap(fn):
                return fn
            return _wrap

        fake.whitelist = _whitelist

        def _logger():
            return types.SimpleNamespace(
                info=lambda *a, **k: None,
                debug=lambda *a, **k: None,
                warning=lambda *a, **k: None,
                error=lambda *a, **k: None,
                exception=lambda *a, **k: None,
            )

        fake.logger = _logger
        # frappe.log_error: capture calls so tests can assert
        fake._captured_log_errors = []

        def _log_error(title=None, message=None, reference_doctype=None, reference_name=None, defer_insert=False):
            fake._captured_log_errors.append({
                "title": title, "message": message,
                "reference_doctype": reference_doctype,
                "reference_name": reference_name,
            })

        fake.log_error = _log_error
        fake._captured_enqueue = []

        def _enqueue(method, queue="default", job_name=None, enqueue_after_commit=False, **kw):
            fake._captured_enqueue.append({
                "method": method, "queue": queue, "job_name": job_name,
                "enqueue_after_commit": enqueue_after_commit,
                "kwargs": kw,
            })

        fake.enqueue = _enqueue

        class _DB:
            def get_single_value(self, *a, **k):
                return None
            def exists(self, *a, **k):
                return False
            def count(self, *a, **k):
                return 0

        fake.db = _DB()

        # frappe.utils stub
        utils_mod = types.ModuleType("frappe.utils")
        utils_mod.escape_html = lambda s: str(s).replace("<", "&lt;").replace(">", "&gt;")
        utils_mod.now = lambda: "2026-05-02 00:00:00"
        utils_mod.now_datetime = lambda: __import__("datetime").datetime(2026, 5, 2, 0, 0, 0)
        utils_mod.get_datetime = lambda v: __import__("datetime").datetime(2026, 5, 2, 0, 0, 0)
        utils_mod.add_to_date = lambda d, **k: d
        utils_mod.get_url = lambda: "https://sandbox.example.com"
        sys.modules["frappe.utils"] = utils_mod
        fake.utils = utils_mod

        sys.modules["frappe"] = fake


_install_stubs()

import frappe  # noqa: E402
from raven_ai_agent.bug_reporter.fingerprint import fingerprint  # noqa: E402
from raven_ai_agent.bug_reporter.redactor import (  # noqa: E402
    redact, redact_secrets, redact_pii, redact_dict,
)
from raven_ai_agent.bug_reporter import collector  # noqa: E402
from raven_ai_agent.bug_reporter import setup as setup_mod  # noqa: E402
from unittest import mock  # noqa: E402


# -------------------------- redactor ------------------------------------- #
def test_redact_secrets_strips_openai_key():
    out = redact_secrets("the key is sk-proj-9gwQ4pOv6a8o7zVC1kNUOGaa")
    assert "<REDACTED:LLM_KEY>" in out
    assert "sk-proj-9gwQ4pOv6a8o7zVC1kNUOGaa" not in out
    print("test_redact_secrets_strips_openai_key OK")


def test_redact_secrets_strips_github_pat():
    out = redact_secrets("auth=ghp_abcdefghijklmnopqrstuvwxyz0123456789")
    assert "<REDACTED:GITHUB_PAT>" in out
    print("test_redact_secrets_strips_github_pat OK")


def test_redact_secrets_strips_bearer_and_jwt():
    src = (
        "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0."
        "X9dRWlGv0UyUcW5oiBgFdkP9V8O1Z3wMrVrjBNqnP-c"
    )
    out = redact_secrets(src)
    # JWT-shaped Bearer token catches the JWT pattern (3 base64 segments).
    assert "<REDACTED:JWT>" in out or "Bearer <REDACTED>" in out
    print("test_redact_secrets_strips_bearer_and_jwt OK")


def test_redact_pii_strips_email_phone():
    out = redact_pii("contact luis@example.com or +52 55 1234 5678")
    assert "<EMAIL>" in out
    assert "<PHONE>" in out
    assert "luis@example.com" not in out
    print("test_redact_pii_strips_email_phone OK")


def test_redact_keeps_doc_ids():
    out = redact("Diagnose SAL-QTN-2024-00783 and SO-00752", strip_pii=True)
    assert "SAL-QTN-2024-00783" in out
    assert "SO-00752" in out
    print("test_redact_keeps_doc_ids OK")


def test_redact_dict_blanks_password_keys():
    out = redact_dict({"openai_api_key": "sk-realsecret123", "name": "Luis"})
    assert out["openai_api_key"] == "<REDACTED>"
    assert out["name"] == "Luis"
    print("test_redact_dict_blanks_password_keys OK")


# ------------------------ fingerprint ------------------------------------ #
def test_fingerprint_stable_across_doc_ids():
    a = fingerprint(bot="task_validator", intent="diagnose",
                    exception_type="ValueError",
                    error_summary="Quotation SAL-QTN-2024-00783 not found")
    b = fingerprint(bot="task_validator", intent="diagnose",
                    exception_type="ValueError",
                    error_summary="Quotation SAL-QTN-2024-00999 not found")
    assert a == b, "fingerprint should ignore specific doc IDs"
    print("test_fingerprint_stable_across_doc_ids OK")


def test_fingerprint_diverges_on_bot():
    a = fingerprint(bot="task_validator", intent="diagnose", error_summary="boom")
    b = fingerprint(bot="payment_bot",    intent="diagnose", error_summary="boom")
    assert a != b
    print("test_fingerprint_diverges_on_bot OK")


def test_fingerprint_diverges_on_failure_class():
    a = fingerprint(bot="x", intent="y", failure_class="exception", error_summary="boom")
    b = fingerprint(bot="x", intent="y", failure_class="reflection_rejected", error_summary="boom")
    assert a != b
    print("test_fingerprint_diverges_on_failure_class OK")


def test_fingerprint_is_8_hex_chars():
    fp = fingerprint(bot="x", intent="y", error_summary="z")
    assert len(fp) == 8
    int(fp, 16)  # parses as hex
    print("test_fingerprint_is_8_hex_chars OK")


# ------------------------ collector -------------------------------------- #
def test_capture_disabled_returns_none():
    os.environ.pop("RAVEN_BUG_REPORTER", None)
    frappe._captured_log_errors.clear()
    frappe._captured_enqueue.clear()
    fp = collector.capture(bot="x", intent="y", failure_class="exception")
    assert fp is None
    assert not frappe._captured_log_errors
    assert not frappe._captured_enqueue
    print("test_capture_disabled_returns_none OK")


def test_capture_enabled_logs_and_enqueues():
    os.environ["RAVEN_BUG_REPORTER"] = "1"
    frappe._captured_log_errors.clear()
    frappe._captured_enqueue.clear()
    try:
        raise RuntimeError("simulated payment_bot crash on SO-00752")
    except RuntimeError as exc:
        fp = collector.capture(
            severity="High",
            bot="payment_bot",
            intent="payment",
            user="luis@example.com",
            query="@ai !payment submit ACC-PAY-2026-00001",
            exception=exc,
        )
    assert fp is not None and len(fp) == 8
    # Error Log called
    assert len(frappe._captured_log_errors) == 1
    title = frappe._captured_log_errors[0]["title"]
    assert "[Raven Bug:High:" in title and fp in title
    assert frappe._captured_log_errors[0]["reference_doctype"] == "Raven Agent Bug"
    assert frappe._captured_log_errors[0]["reference_name"] == fp
    # Email leaked into title? Should be redacted in body
    body = frappe._captured_log_errors[0]["message"]
    assert "luis@example.com" in body or "<EMAIL>" in body  # PII not stripped at error log layer
    # Enqueue happened
    assert len(frappe._captured_enqueue) == 1
    assert frappe._captured_enqueue[0]["method"] == "raven_ai_agent.bug_reporter.tasks.publish_bug"
    assert frappe._captured_enqueue[0]["queue"] == "short"
    assert frappe._captured_enqueue[0]["enqueue_after_commit"] is True
    assert frappe._captured_enqueue[0]["job_name"] == f"bug_reporter:{fp}"
    print("test_capture_enabled_logs_and_enqueues OK")


def test_capture_strips_secrets_in_payload():
    os.environ["RAVEN_BUG_REPORTER"] = "1"
    frappe._captured_log_errors.clear()
    frappe._captured_enqueue.clear()
    try:
        raise RuntimeError("auth failed sk-proj-9gwQ4pOv6a8o7zVC1kNUOGaaIri5BLCZ")
    except RuntimeError as exc:
        collector.capture(
            severity="High",
            bot="x",
            user="u",
            query="header was Authorization: Bearer ghp_abcdefghijklmnopqrstuvwxyz0123456789",
            exception=exc,
        )
    body = frappe._captured_log_errors[0]["message"]
    assert "sk-proj-9gwQ4pOv6a8o7zVC1kNUOGaa" not in body, body
    assert "ghp_abcdefghijklmnopqrstuvwxyz0123456789" not in body, body
    payload = frappe._captured_enqueue[0]["kwargs"]["payload"]
    assert "sk-proj-9gwQ4pOv" not in str(payload)
    assert "ghp_abcdefghijklmnopqrstuvwxyz0123456789" not in str(payload)
    print("test_capture_strips_secrets_in_payload OK")


# ---------------------- setup / fork syncer ------------------------------ #
class _FakeResponse:
    def __init__(self, status_code, json_body=None, text=""):
        self.status_code = status_code
        self._json = json_body or {}
        self.text = text

    def json(self):
        return self._json


def _make_router(routes):
    """routes is a list of (method, url_substring, response). The first matching
    entry pops off the queue (FIFO per match), so call order is enforced.
    """
    queue = list(routes)

    def _route(method, url, **kwargs):
        for i, (m, sub, resp) in enumerate(queue):
            if m == method and sub in url:
                queue.pop(i)
                return resp
        raise AssertionError(f"unexpected request: {method} {url}")

    return _route


def test_sync_fork_uses_upstream_default_branch():
    """When upstream default_branch is V13.5.0, the ref-update PATCH must
    target V13.5.0 — not the hardcoded 'main'."""
    captured_patch_urls = []

    def fake_get(url, headers=None, timeout=None):
        if "/repos/rogerboy38/amb_print_app" in url and "/git/" not in url:
            return _FakeResponse(200, {"default_branch": "V13.5.0"})
        if "/git/ref/heads/V13.5.0" in url:
            return _FakeResponse(200, {"object": {"sha": "old_sha"}})
        raise AssertionError(f"unexpected GET: {url}")

    def fake_patch(url, headers=None, json=None, timeout=None):
        captured_patch_urls.append(url)
        return _FakeResponse(200, {"object": {"sha": json.get("sha")}})

    def fake_post(url, headers=None, json=None, timeout=None):
        # snapshot branch creation
        return _FakeResponse(201, {})

    with mock.patch.object(setup_mod.requests, "get", side_effect=fake_get), \
         mock.patch.object(setup_mod.requests, "patch", side_effect=fake_patch), \
         mock.patch.object(setup_mod.requests, "post", side_effect=fake_post):
        out = setup_mod._sync_fork_to_sha(
            fork_owner="rogerboy38bis",
            repo="amb_print_app",
            upstream_owner="rogerboy38",
            sha="new_sha_1234",
            snapshot_branch="prod-snapshot-2026-05-02-abcdef12",
            headers={"Authorization": "Bearer x"},
        )

    assert out["default_branch"] == "V13.5.0", out
    assert out["main_sync"] == "fast_forward", out
    assert any("/git/ref/heads/V13.5.0" in u for u in captured_patch_urls), captured_patch_urls
    assert not any("/git/ref/heads/main" in u for u in captured_patch_urls), captured_patch_urls
    print("test_sync_fork_uses_upstream_default_branch OK")


def test_visibility_422_is_soft_warning():
    """A 422 from the visibility PATCH must surface as
    visibility='skipped_public_parent_policy' and must NOT raise."""

    def fake_get(url, headers=None, timeout=None):
        # fork lookup: exists, currently public
        if "/repos/rogerboy38bis/amb_print_app" in url:
            return _FakeResponse(
                200,
                {"html_url": "https://github.com/rogerboy38bis/amb_print_app",
                 "private": False},
            )
        raise AssertionError(f"unexpected GET: {url}")

    def fake_patch(url, headers=None, json=None, timeout=None):
        return _FakeResponse(422, text="cannot make fork private")

    with mock.patch.object(setup_mod.requests, "get", side_effect=fake_get), \
         mock.patch.object(setup_mod.requests, "patch", side_effect=fake_patch):
        result = setup_mod._ensure_fork(
            "amb_print_app", "rogerboy38", "rogerboy38bis",
            headers={"Authorization": "Bearer x"},
        )

    assert result["action"] == "exists", result
    assert result["visibility"] == "skipped_public_parent_policy", result
    assert "visibility_patch_status" not in result, result
    print("test_visibility_422_is_soft_warning OK")


def test_fork_readiness_poll_exhaustion_returns_created_pending():
    """When wait_for_fork_ready never sees a 200, _ensure_fork returns
    action='created_pending'."""

    get_calls = {"n": 0}

    def fake_get(url, headers=None, timeout=None):
        # First call: fork lookup -> 404 (does not exist yet)
        # All branch-readiness polls -> 404
        # The upstream-default-branch fallback (if invoked) -> 200
        if "/branches/V13.5.0" in url:
            get_calls["n"] += 1
            return _FakeResponse(404, text="branch not yet created")
        if url.endswith("/repos/rogerboy38/amb_print_app"):
            return _FakeResponse(200, {"default_branch": "V13.5.0"})
        if url.endswith("/repos/rogerboy38bis/amb_print_app"):
            return _FakeResponse(404, text="not found")
        raise AssertionError(f"unexpected GET: {url}")

    def fake_post(url, headers=None, json=None, timeout=None):
        # Fork-create call
        return _FakeResponse(
            202,
            {"html_url": "https://github.com/rogerboy38bis/amb_print_app",
             "default_branch": "V13.5.0"},
        )

    def fake_patch(url, headers=None, json=None, timeout=None):
        raise AssertionError("PATCH should not be called when fork not ready")

    with mock.patch.object(setup_mod.requests, "get", side_effect=fake_get), \
         mock.patch.object(setup_mod.requests, "post", side_effect=fake_post), \
         mock.patch.object(setup_mod.requests, "patch", side_effect=fake_patch), \
         mock.patch.object(setup_mod.time, "sleep", lambda *_a, **_k: None):
        result = setup_mod._ensure_fork(
            "amb_print_app", "rogerboy38", "rogerboy38bis",
            headers={"Authorization": "Bearer x"},
        )

    assert result["action"] == "created_pending", result
    assert result["default_branch"] == "V13.5.0", result
    assert get_calls["n"] == setup_mod._FORK_READY_MAX_ATTEMPTS, get_calls
    print("test_fork_readiness_poll_exhaustion_returns_created_pending OK")


# --------------------------- main ---------------------------------------- #
if __name__ == "__main__":
    test_redact_secrets_strips_openai_key()
    test_redact_secrets_strips_github_pat()
    test_redact_secrets_strips_bearer_and_jwt()
    test_redact_pii_strips_email_phone()
    test_redact_keeps_doc_ids()
    test_redact_dict_blanks_password_keys()
    test_fingerprint_stable_across_doc_ids()
    test_fingerprint_diverges_on_bot()
    test_fingerprint_diverges_on_failure_class()
    test_fingerprint_is_8_hex_chars()
    test_capture_disabled_returns_none()
    test_capture_enabled_logs_and_enqueues()
    test_capture_strips_secrets_in_payload()
    test_sync_fork_uses_upstream_default_branch()
    test_visibility_422_is_soft_warning()
    test_fork_readiness_poll_exhaustion_returns_created_pending()
    print("\nAll bug reporter smoke tests passed.")
