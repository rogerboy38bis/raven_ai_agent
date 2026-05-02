"""
One-time bootstrap helper.

Run from any environment that has the rogerboy38bis PAT configured:

    bench --site sandbox.sysmayal.cloud execute \\
        raven_ai_agent.bug_reporter.setup.bootstrap_forks

Idempotent: skips repos that already exist, and only flips visibility to
private when the fork is currently public.
"""
from __future__ import annotations

import json
from typing import Iterable, List

import frappe

try:
    import requests
    HAVE_REQUESTS = True
except ImportError:  # pragma: no cover
    HAVE_REQUESTS = False


# Upstream repo names on rogerboy38.  Verified against the live account on
# 2026-05-02: 'amb_print_app' is the canonical repo name (NOT 'amb_print').
_DEFAULT_APPS = ("raven_ai_agent", "amb_w_spc", "amb_w_tds", "amb_print_app")
_UPSTREAM_OWNER_DEFAULT = "rogerboy38"
_FORK_OWNER_DEFAULT = "rogerboy38bis"
_GITHUB_API = "https://api.github.com"


@frappe.whitelist()
def bootstrap_forks(apps: str | Iterable[str] | None = None) -> dict:
    """Fork each app from rogerboy38 into rogerboy38bis (private).

    apps: comma-separated string OR list.  Defaults to the four amb apps.
    Returns {app: {action, url, status_code}} so you can audit the run.
    """
    if not HAVE_REQUESTS:
        return {"error": "requests package not available"}

    token = _get_token()
    if not token:
        return {
            "error": "no PAT configured. Set bug_reporter_github_token via "
                     "site_config.json or AI Agent Settings."
        }

    upstream_owner = _conf("bug_reporter_github_upstream_owner", _UPSTREAM_OWNER_DEFAULT)
    fork_owner = _conf("bug_reporter_github_owner", _FORK_OWNER_DEFAULT)

    if isinstance(apps, str):
        app_list: List[str] = [a.strip() for a in apps.split(",") if a.strip()]
    elif apps:
        app_list = list(apps)
    else:
        app_list = list(_DEFAULT_APPS)

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "raven_ai_agent-bug-reporter-setup",
    }

    summary: dict = {}
    for app in app_list:
        summary[app] = _ensure_fork(app, upstream_owner, fork_owner, headers)

    return {
        "upstream_owner": upstream_owner,
        "fork_owner": fork_owner,
        "results": summary,
    }


# ---- internals ----------------------------------------------------------- #
def _ensure_fork(app: str, upstream_owner: str, fork_owner: str, headers: dict) -> dict:
    """Ensure rogerboy38bis/<app> exists as a private fork of rogerboy38/<app>."""
    fork_url = f"{_GITHUB_API}/repos/{fork_owner}/{app}"

    # Already exists?
    r = requests.get(fork_url, headers=headers, timeout=10)
    if r.status_code == 200:
        result = {"action": "exists", "url": r.json().get("html_url")}
        # Make private if currently public.
        if r.json().get("private") is False:
            r2 = requests.patch(fork_url, headers=headers, json={"private": True}, timeout=10)
            result["visibility_patch_status"] = r2.status_code
        return result

    if r.status_code != 404:
        return {"action": "lookup_failed", "status_code": r.status_code, "body": r.text[:200]}

    # Create fork.
    create_url = f"{_GITHUB_API}/repos/{upstream_owner}/{app}/forks"
    # name= keeps the same name; default_branch_only=True keeps it lean.
    body = {"default_branch_only": True}
    # If forking into a different USER (not org) the PAT account, leave 'organization' off.
    r3 = requests.post(create_url, headers=headers, json=body, timeout=20)
    if r3.status_code not in (201, 202):
        return {"action": "fork_failed", "status_code": r3.status_code, "body": r3.text[:200]}

    new_url = (r3.json() or {}).get("html_url")

    # Forks are public by default; flip to private.
    r4 = requests.patch(fork_url, headers=headers, json={"private": True}, timeout=10)
    return {
        "action": "forked",
        "url": new_url,
        "visibility_patch_status": r4.status_code,
    }


def _get_token() -> str | None:
    try:
        from raven_ai_agent.providers._secrets import resolve_secret
        return resolve_secret(
            settings={},
            env_vars=("RAVEN_BUG_REPORTER_GITHUB_TOKEN", "GITHUB_TOKEN"),
            site_config_keys=("bug_reporter_github_token",),
            db_field="bug_reporter_github_token",
            label="Bug Reporter GitHub PAT",
            required=False,
        )
    except Exception:  # noqa: BLE001
        return None


def _conf(key: str, default: str) -> str:
    try:
        v = (frappe.conf or {}).get(key)
        if v:
            return str(v)
    except Exception:  # noqa: BLE001
        pass
    try:
        v = frappe.db.get_single_value("AI Agent Settings", key)
        if v:
            return str(v)
    except Exception:  # noqa: BLE001
        pass
    return default
