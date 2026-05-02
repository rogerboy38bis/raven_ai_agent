"""
Secret resolution helper for LLM providers.

Why this exists
---------------
``frappe.get_single("AI Agent Settings").as_dict()`` returns Password fields
as masked stars (``"********"``) instead of the real value.  Every provider
in this app currently does:

    api_key = settings.get("openai_api_key")          # masked stars (truthy!)
    if not api_key:                                    # never True
        api_key = agent_settings.get_password(...)     # never reached

so the OpenAI/DeepSeek/Claude/MiniMax client gets initialized with the masked
stars and OpenAI rejects every call with HTTP 401.

This helper centralizes secret resolution and fixes the bug in one place.

Resolution order (first non-empty wins)
---------------------------------------
1. Environment variable (e.g. ``RAVEN_OPENAI_API_KEY`` or the standard
   ``OPENAI_API_KEY``).  Survives DB restores and encryption_key mismatches.
2. ``site_config.json``  via ``frappe.conf`` (e.g. ``"openai_api_key"``).
   Survives encryption_key mismatches.
3. The encrypted Password field in the DB, decrypted properly via
   ``get_decrypted_password`` (NOT via ``as_dict()``).
4. ``settings`` dict — but ONLY if the value doesn't look like masked stars,
   so we never accidentally use the placeholder.

If every step fails, raises ``ValueError`` with a clear message.
"""
from __future__ import annotations

import os
import re
from typing import Dict, Iterable, Optional

import frappe

_MASKED_STARS_RE = re.compile(r"^\*+$")


def _looks_masked(value: Optional[str]) -> bool:
    """True for values like '*****...' that come from .as_dict() on Password fields."""
    if not value:
        return True
    return bool(_MASKED_STARS_RE.match(value.strip()))


def _from_env(env_vars: Iterable[str]) -> Optional[str]:
    for name in env_vars:
        v = os.environ.get(name)
        if v and not _looks_masked(v):
            return v.strip()
    return None


def _from_site_config(keys: Iterable[str]) -> Optional[str]:
    try:
        conf = frappe.conf or {}
    except Exception:  # noqa: BLE001
        return None
    for k in keys:
        v = conf.get(k)
        if v and not _looks_masked(v):
            return str(v).strip()
    return None


def _from_db(doctype: str, fieldname: str) -> Optional[str]:
    """Decrypt the Password field properly.  Returns None on any failure
    (missing field, invalid token from a stale encryption_key, etc).  We
    never want a broken DB secret to crash the agent if env / site_config
    can provide the value."""
    try:
        from frappe.utils.password import get_decrypted_password

        v = get_decrypted_password(doctype, doctype, fieldname, raise_exception=False)
        if v and not _looks_masked(v):
            return v.strip()
    except Exception as exc:  # noqa: BLE001
        frappe.logger().debug(
            f"[secrets] get_decrypted_password({doctype}.{fieldname}) failed: {exc}"
        )
    return None


def _from_settings(settings: Dict, settings_keys: Iterable[str]) -> Optional[str]:
    """settings comes from ``as_dict()``; treat masked stars as missing."""
    for k in settings_keys:
        v = settings.get(k)
        if v and not _looks_masked(str(v)):
            return str(v).strip()
    return None


def resolve_secret(
    settings: Dict,
    *,
    env_vars: Iterable[str],
    site_config_keys: Iterable[str],
    db_field: str,
    settings_keys: Optional[Iterable[str]] = None,
    db_doctype: str = "AI Agent Settings",
    required: bool = True,
    label: Optional[str] = None,
) -> Optional[str]:
    """Resolve a provider secret with a robust fallback chain.

    Parameters
    ----------
    settings           : the ``settings`` dict each provider already receives.
    env_vars           : env vars to try, in order.  Prefer namespaced names
                         like ``RAVEN_OPENAI_API_KEY`` to avoid colliding with
                         the user's shell environment.
    site_config_keys   : keys to look up in ``site_config.json``.
    db_field           : Password fieldname on ``db_doctype``.
    settings_keys      : keys in the ``settings`` dict — only used as a last
                         resort because they often contain masked stars.
    db_doctype         : Single doctype that holds the field.
    required           : If True (default), raise ValueError when nothing
                         resolves.
    label              : Human-friendly name for the error message.

    Returns
    -------
    The resolved secret string, or None if not required and nothing found.
    """
    settings_keys = list(settings_keys or [db_field])

    for source_name, getter in (
        ("env", lambda: _from_env(env_vars)),
        ("site_config", lambda: _from_site_config(site_config_keys)),
        ("db", lambda: _from_db(db_doctype, db_field)),
        ("settings", lambda: _from_settings(settings, settings_keys)),
    ):
        v = getter()
        if v:
            frappe.logger().debug(f"[secrets] resolved {label or db_field} from {source_name}")
            return v

    if required:
        raise ValueError(
            f"{label or db_field} not configured. Set one of: "
            f"env {list(env_vars)}, site_config {list(site_config_keys)}, "
            f"or {db_doctype}.{db_field} in the UI (then re-save)."
        )
    return None
