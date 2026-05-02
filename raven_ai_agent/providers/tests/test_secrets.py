"""
Smoke tests for raven_ai_agent.providers._secrets.resolve_secret.

Run with (no Frappe runtime, no API keys, no network):
    cd ~/frappe-bench/apps/raven_ai_agent
    PYTHONPATH=. python3 raven_ai_agent/providers/tests/test_secrets.py

(``python -m`` would trigger the providers/__init__.py side-effect imports
before our stubs install; running the file directly avoids that.)
"""
from __future__ import annotations

import os
import sys
import types

# --- Frappe stub --- must run BEFORE any provider import.
def _install_frappe_stub():
    if "frappe" in sys.modules:
        return
    fake = types.ModuleType("frappe")
    fake.conf = {}
    fake.logger = lambda: types.SimpleNamespace(debug=lambda *a, **kw: None)

    pw_mod = types.ModuleType("frappe.utils.password")
    _STORE = {}

    def get_decrypted_password(doctype, name, fieldname, raise_exception=True):
        return _STORE.get((doctype, fieldname))

    pw_mod.get_decrypted_password = get_decrypted_password
    pw_mod._store = _STORE

    utils_mod = types.ModuleType("frappe.utils")
    utils_mod.password = pw_mod

    fake.utils = utils_mod
    sys.modules["frappe"] = fake
    sys.modules["frappe.utils"] = utils_mod
    sys.modules["frappe.utils.password"] = pw_mod


_install_frappe_stub()

# Stub heavy provider deps so importing the providers package doesn't fail.
for _opt in ("openai", "anthropic", "httpx"):
    if _opt not in sys.modules:
        _stub = types.ModuleType(_opt)
        if _opt == "openai":
            _stub.OpenAI = lambda **kw: None
        if _opt == "anthropic":
            _stub.Anthropic = lambda **kw: None
        sys.modules[_opt] = _stub


import frappe  # noqa: E402
from frappe.utils import password as fpw  # noqa: E402

from raven_ai_agent.providers._secrets import resolve_secret, _looks_masked  # noqa: E402


def _reset():
    os.environ.pop("RAVEN_OPENAI_API_KEY", None)
    os.environ.pop("OPENAI_API_KEY", None)
    frappe.conf = {}
    fpw._store.clear()


def test_looks_masked():
    assert _looks_masked("**************")
    assert _looks_masked("")
    assert _looks_masked(None)
    assert not _looks_masked("sk-proj-abc")
    assert not _looks_masked("real-key-123")
    print("test_looks_masked OK")


def test_env_wins():
    _reset()
    os.environ["RAVEN_OPENAI_API_KEY"] = "sk-from-env"
    frappe.conf = {"openai_api_key": "sk-from-conf"}
    fpw._store[("AI Agent Settings", "openai_api_key")] = "sk-from-db"
    out = resolve_secret(
        {"openai_api_key": "sk-from-settings"},
        env_vars=("RAVEN_OPENAI_API_KEY", "OPENAI_API_KEY"),
        site_config_keys=("openai_api_key",),
        db_field="openai_api_key",
        settings_keys=("openai_api_key",),
        label="OpenAI",
    )
    assert out == "sk-from-env", out
    print("test_env_wins OK")


def test_site_config_used_when_no_env():
    _reset()
    frappe.conf = {"openai_api_key": "sk-from-conf"}
    fpw._store[("AI Agent Settings", "openai_api_key")] = "sk-from-db"
    out = resolve_secret(
        {"openai_api_key": "************"},
        env_vars=("RAVEN_OPENAI_API_KEY",),
        site_config_keys=("openai_api_key",),
        db_field="openai_api_key",
    )
    assert out == "sk-from-conf", out
    print("test_site_config_used_when_no_env OK")


def test_db_used_when_no_env_no_conf():
    _reset()
    fpw._store[("AI Agent Settings", "openai_api_key")] = "sk-from-db"
    out = resolve_secret(
        {"openai_api_key": "************"},  # masked, must be ignored
        env_vars=("RAVEN_OPENAI_API_KEY",),
        site_config_keys=("openai_api_key",),
        db_field="openai_api_key",
    )
    assert out == "sk-from-db", out
    print("test_db_used_when_no_env_no_conf OK")


def test_masked_settings_value_is_rejected():
    _reset()
    out = resolve_secret(
        {"openai_api_key": "********"},  # only source available, but masked
        env_vars=("RAVEN_OPENAI_API_KEY",),
        site_config_keys=("openai_api_key",),
        db_field="openai_api_key",
        required=False,
    )
    assert out is None, f"masked stars must NOT resolve, got {out!r}"
    print("test_masked_settings_value_is_rejected OK")


def test_required_raises_when_nothing_resolves():
    _reset()
    raised = False
    try:
        resolve_secret(
            {"openai_api_key": "********"},
            env_vars=("RAVEN_OPENAI_API_KEY",),
            site_config_keys=("openai_api_key",),
            db_field="openai_api_key",
            required=True,
        )
    except ValueError:
        raised = True
    assert raised, "required=True must raise when nothing resolves"
    print("test_required_raises_when_nothing_resolves OK")


def test_real_settings_value_is_accepted():
    _reset()
    out = resolve_secret(
        {"openai_api_key": "sk-real-from-settings"},
        env_vars=("RAVEN_OPENAI_API_KEY",),
        site_config_keys=("openai_api_key",),
        db_field="openai_api_key",
    )
    assert out == "sk-real-from-settings"
    print("test_real_settings_value_is_accepted OK")


if __name__ == "__main__":
    test_looks_masked()
    test_env_wins()
    test_site_config_used_when_no_env()
    test_db_used_when_no_env_no_conf()
    test_masked_settings_value_is_rejected()
    test_required_raises_when_nothing_resolves()
    test_real_settings_value_is_accepted()
    print("\nAll secret resolver tests passed.")
