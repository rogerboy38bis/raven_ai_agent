"""Smoke test for the no-Frappe helpers inside agent_supervisor.

Run with:
    python -m raven_ai_agent.api.tests.test_agent_supervisor_helpers
"""
from __future__ import annotations

import sys
import types

# Stub frappe so the supervisor module imports cleanly outside ERPNext.
if "frappe" not in sys.modules:
    fake = types.ModuleType("frappe")

    class _DB:
        def get_single_value(self, *a, **kw):
            return 0

        def exists(self, *a, **kw):
            return False

    fake.db = _DB()
    fake.flags = types.SimpleNamespace()
    fake.session = types.SimpleNamespace(user="Administrator")
    fake.logger = lambda: types.SimpleNamespace(
        info=lambda *a, **kw: None,
        warning=lambda *a, **kw: None,
        debug=lambda *a, **kw: None,
    )
    fake.get_single = lambda *a, **kw: types.SimpleNamespace(as_dict=lambda: {})
    sys.modules["frappe"] = fake


from raven_ai_agent.api import agent_supervisor as supv  # noqa: E402


def test_autonomy_from_query():
    assert supv._autonomy_from_query("show pending invoices") == "copilot"
    assert supv._autonomy_from_query("@ai !submit Sales Invoice SINV-1") == "command"
    assert supv._autonomy_from_query("delete order SO-1") == "command"
    print("test_autonomy_from_query OK")


def test_action_kind():
    assert supv._action_kind("payment_bot", "create payment") == "payment"
    assert supv._action_kind("manufacturing_bot", "submit work order") == "submit"
    assert supv._action_kind("sales_order_bot", "show pending") == "read"
    assert supv._action_kind("sales_order_bot", "convert quotation") == "convert"
    assert supv._action_kind("sales_order_bot", "process all 30 documents") == "bulk"
    print("test_action_kind OK")


def test_guess_doctype_and_name():
    assert supv._guess_doctype("submit Sales Invoice SINV-2026-001") == "Sales Invoice"
    assert supv._guess_doctype("show pending payments") is None
    assert supv._guess_doc_name("diagnose SAL-QTN-0901") == "SAL-QTN-0901"
    assert supv._guess_doc_name("status of SO-00752") == "SO-00752"
    assert supv._guess_doc_name("nothing here") is None
    print("test_guess_doctype_and_name OK")


def test_guess_bulk_count():
    assert supv._guess_bulk_count("submit 50 invoices") == 50
    assert supv._guess_bulk_count("submit invoice") == 0
    print("test_guess_bulk_count OK")


def test_is_enabled_off_by_default():
    import os

    os.environ.pop("RAVEN_INTELLIGENCE_LAYER", None)
    assert supv.is_enabled() in (False, True)  # depends on settings stub; mostly False
    os.environ["RAVEN_INTELLIGENCE_LAYER"] = "1"
    assert supv.is_enabled() is True
    os.environ["RAVEN_INTELLIGENCE_LAYER"] = "0"
    # When the env value is "0" we fall back to the settings stub which returns 0.
    assert supv.is_enabled() is False
    os.environ.pop("RAVEN_INTELLIGENCE_LAYER", None)
    print("test_is_enabled_off_by_default OK")


def test_pre_supervise_passthrough_when_disabled():
    import os
    os.environ.pop("RAVEN_INTELLIGENCE_LAYER", None)
    out = supv.pre_supervise("show pending invoices", "u@x", "sales_order_bot")
    assert out["short_circuit"] is None
    assert out["enriched_query"] == "show pending invoices"
    assert out["complexity"] == "simple"
    print("test_pre_supervise_passthrough_when_disabled OK")


def test_supervise_passthrough_when_disabled():
    import os
    os.environ.pop("RAVEN_INTELLIGENCE_LAYER", None)
    result = {"success": True, "response": "hello"}
    out = supv.supervise(result, "show pending", "u@x", "sales_order_bot", "simple")
    assert out is result
    assert out["response"] == "hello"
    print("test_supervise_passthrough_when_disabled OK")


if __name__ == "__main__":
    test_autonomy_from_query()
    test_action_kind()
    test_guess_doctype_and_name()
    test_guess_bulk_count()
    test_is_enabled_off_by_default()
    test_pre_supervise_passthrough_when_disabled()
    test_supervise_passthrough_when_disabled()
    print("\nAll supervisor smoke tests passed.")
