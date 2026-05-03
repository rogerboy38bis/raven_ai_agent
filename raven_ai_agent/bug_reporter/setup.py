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
import logging
import time
from typing import Iterable, List

import frappe

_log = logging.getLogger(__name__)

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


# Frappe-app -> GitHub-repo translation when names differ on the bis side.
# Keep aligned with bug_reporter.destinations.github._FRAPPE_APP_TO_GITHUB_REPO.
_FRAPPE_APP_TO_GITHUB_REPO = {
    "amb_print": "amb_print_app",
}


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
        repo_name = _FRAPPE_APP_TO_GITHUB_REPO.get(app, app)
        summary[app] = _ensure_fork(repo_name, upstream_owner, fork_owner, headers)

    return {
        "upstream_owner": upstream_owner,
        "fork_owner": fork_owner,
        "results": summary,
    }


# ---------------------------------------------------------------------------
# sync_forks_from_prod_state
# ---------------------------------------------------------------------------
@frappe.whitelist()
def sync_forks_from_prod_state(
    state_path: str,
    snapshot_branch_prefix: str = "prod-snapshot",
) -> dict:
    """Read a prod_state.json (produced by scripts/capture_prod_state.sh on
    prod) and ensure each owned app has a fork on rogerboy38bis whose ``main``
    matches the prod SHA, AND a snapshot branch like
    ``prod-snapshot-2026-05-02-abc12345`` pointing at the same commit.

    Only apps whose upstream_owner equals ``bug_reporter_github_upstream_owner``
    (default 'rogerboy38') are synced.  Vendored upstreams (frappe, erpnext,
    raven, ...) are intentionally skipped.
    """
    if not HAVE_REQUESTS:
        return {"error": "requests package not available"}

    token = _get_token()
    if not token:
        return {"error": "no PAT configured"}

    state = _load_state(state_path)
    if "error" in state:
        return state

    upstream_owner = _conf("bug_reporter_github_upstream_owner", _UPSTREAM_OWNER_DEFAULT)
    fork_owner = _conf("bug_reporter_github_owner", _FORK_OWNER_DEFAULT)

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "raven_ai_agent-bug-reporter-sync",
    }

    # Build a stable snapshot suffix from the captured_at timestamp.
    captured_at = (state.get("captured_at") or "")[:10] or "prod"
    suffix = captured_at.replace(":", "-").replace("T", "-")

    summary: dict = {}
    for entry in state.get("apps", []) or []:
        app = entry.get("app") or ""
        owner = entry.get("upstream_owner") or ""
        if owner != upstream_owner:
            summary[app] = {"action": "skipped", "reason": f"owner={owner}"}
            continue

        upstream_repo = entry.get("upstream_repo") or _FRAPPE_APP_TO_GITHUB_REPO.get(app, app)
        sha = entry.get("sha") or ""
        if not sha:
            summary[app] = {"action": "skipped", "reason": "no SHA"}
            continue

        # Step 1: ensure the fork itself exists.
        ensure = _ensure_fork(upstream_repo, upstream_owner, fork_owner, headers)
        # Step 2: sync fork's main to the prod SHA, AND create snapshot branch.
        sync = _sync_fork_to_sha(
            fork_owner, upstream_repo, upstream_owner, sha,
            snapshot_branch=f"{snapshot_branch_prefix}-{suffix}-{(entry.get('short_sha') or sha[:8])}",
            headers=headers,
        )
        summary[app] = {
            "upstream_repo": upstream_repo,
            "sha": sha,
            "latest_tag": entry.get("latest_tag") or None,
            "tag_distance": entry.get("tag_distance") or None,
            "dirty": entry.get("dirty"),
            "fork": ensure,
            "sync": sync,
        }

    return {
        "captured_at": state.get("captured_at"),
        "captured_on": state.get("captured_on"),
        "upstream_owner": upstream_owner,
        "fork_owner": fork_owner,
        "results": summary,
    }


def _load_state(state_path: str) -> dict:
    try:
        with open(state_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {"error": f"state file not found: {state_path}"}
    except json.JSONDecodeError as exc:
        return {"error": f"invalid JSON: {exc}"}


def _get_upstream_default_branch(
    upstream_owner: str, repo: str, headers: dict
) -> str | None:
    """Fetch the upstream repo's default_branch via GET /repos/{owner}/{repo}.

    Different upstream repos use different default branch names (e.g. V13.5.0,
    version-16, main). Hardcoding 'main' produces a 404 on merge-upstream.
    """
    url = f"{_GITHUB_API}/repos/{upstream_owner}/{repo}"
    r = requests.get(url, headers=headers, timeout=10)
    if r.status_code != 200:
        return None
    return (r.json() or {}).get("default_branch") or None


def _sync_fork_to_sha(
    fork_owner: str,
    repo: str,
    upstream_owner: str,
    sha: str,
    snapshot_branch: str,
    headers: dict,
) -> dict:
    """Update fork's default branch to point at the upstream SHA, and create a
    snapshot branch at the same SHA.  Idempotent.
    """
    out: dict = {}

    default_branch = _get_upstream_default_branch(upstream_owner, repo, headers)
    if not default_branch:
        out["main_sync"] = "failed_no_default_branch"
        out["default_branch"] = None
    else:
        out["default_branch"] = default_branch

        # 1. Read the current default-branch SHA on the fork.
        ref_url = f"{_GITHUB_API}/repos/{fork_owner}/{repo}/git/refs/heads/{default_branch}"
        cur = requests.get(ref_url, headers=headers, timeout=10)
        out["current_default_sha"] = (
            (cur.json() or {}).get("object", {}).get("sha")
            if cur.status_code == 200
            else None
        )

        # 2. If different, fast-forward (force=False first, then force=True if needed).
        if out["current_default_sha"] != sha:
            body = {"sha": sha, "force": False}
            ff = requests.patch(ref_url, headers=headers, json=body, timeout=10)
            if ff.status_code in (200, 201):
                out["main_sync"] = "fast_forward"
            else:
                body["force"] = True
                fz = requests.patch(ref_url, headers=headers, json=body, timeout=10)
                out["main_sync"] = (
                    "forced" if fz.status_code in (200, 201) else f"failed_{fz.status_code}"
                )
                if fz.status_code not in (200, 201):
                    out["main_sync_body"] = fz.text[:200]
        else:
            out["main_sync"] = "already_in_sync"

    # 3. Create the snapshot branch (skip if it already exists).
    snap_url = f"{_GITHUB_API}/repos/{fork_owner}/{repo}/git/refs"
    snap_body = {"ref": f"refs/heads/{snapshot_branch}", "sha": sha}
    snap = requests.post(snap_url, headers=headers, json=snap_body, timeout=10)
    if snap.status_code in (200, 201):
        out["snapshot_branch"] = snapshot_branch
    elif snap.status_code == 422:
        # Already exists.
        out["snapshot_branch"] = f"{snapshot_branch} (exists)"
    else:
        out["snapshot_branch_status"] = snap.status_code
        out["snapshot_branch_body"] = snap.text[:200]

    return out


# ---- internals ----------------------------------------------------------- #
_FORK_READY_POLL_INTERVAL_SEC = 2
_FORK_READY_MAX_ATTEMPTS = 30


def _classify_visibility_patch(status_code: int) -> str:
    """Map the visibility-patch HTTP status to a stable semantic string.

    422 is GitHub's "you can't make a fork private when its parent is public on
    this account tier". This is structural, not a bug, so we surface it as a
    soft warning instead of a failure.
    """
    if status_code in (200, 204):
        return "patched_to_private"
    if status_code == 404:
        return "already_set"
    if status_code == 422:
        _log.info(
            "GitHub does not allow private forks of public parent repos via "
            "API on this account tier; fork remains public. This is structural, "
            "not a bug."
        )
        return "skipped_public_parent_policy"
    return f"unexpected_{status_code}"


def wait_for_fork_ready(
    fork_owner: str,
    repo: str,
    default_branch: str,
    headers: dict,
    max_attempts: int = _FORK_READY_MAX_ATTEMPTS,
    poll_interval: float = _FORK_READY_POLL_INTERVAL_SEC,
) -> bool:
    """Poll ``GET /repos/{fork_owner}/{repo}/branches/{default_branch}`` until
    GitHub finishes initializing the fork's refs.

    Returns True if the branch resolves with HTTP 200 within the budget,
    False otherwise. Default budget: 30 attempts * 2s = 60s.
    """
    url = f"{_GITHUB_API}/repos/{fork_owner}/{repo}/branches/{default_branch}"
    for _ in range(max_attempts):
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(poll_interval)
    return False


def _ensure_fork(repo: str, upstream_owner: str, fork_owner: str, headers: dict) -> dict:
    """Ensure ``<fork_owner>/<repo>`` exists as a private fork of
    ``<upstream_owner>/<repo>``.  ``repo`` is the GitHub repo name (which
    may differ from the Frappe app name on disk — see
    ``_FRAPPE_APP_TO_GITHUB_REPO``)."""
    fork_url = f"{_GITHUB_API}/repos/{fork_owner}/{repo}"

    # Already exists?
    r = requests.get(fork_url, headers=headers, timeout=10)
    if r.status_code == 200:
        result = {"action": "exists", "url": r.json().get("html_url")}
        # Make private if currently public.
        if r.json().get("private") is False:
            r2 = requests.patch(fork_url, headers=headers, json={"private": True}, timeout=10)
            result["visibility"] = _classify_visibility_patch(r2.status_code)
        else:
            result["visibility"] = "already_set"
        return result

    if r.status_code != 404:
        return {"action": "lookup_failed", "status_code": r.status_code, "body": r.text[:200]}

    # Create fork.
    create_url = f"{_GITHUB_API}/repos/{upstream_owner}/{repo}/forks"
    # name= keeps the same name; default_branch_only=True keeps it lean.
    body = {"default_branch_only": True}
    # If forking into a different USER (not org) the PAT account, leave 'organization' off.
    r3 = requests.post(create_url, headers=headers, json=body, timeout=20)
    if r3.status_code not in (201, 202):
        return {"action": "fork_failed", "status_code": r3.status_code, "body": r3.text[:200]}

    new_payload = r3.json() or {}
    new_url = new_payload.get("html_url")
    default_branch = (
        new_payload.get("default_branch")
        or _get_upstream_default_branch(upstream_owner, repo, headers)
    )

    # Wait for GitHub to finish initializing the fork's refs before any caller
    # tries to read or update the default branch.
    ready = False
    if default_branch:
        ready = wait_for_fork_ready(fork_owner, repo, default_branch, headers)

    if not ready:
        return {
            "action": "created_pending",
            "url": new_url,
            "default_branch": default_branch,
        }

    # Forks are public by default; flip to private.
    r4 = requests.patch(fork_url, headers=headers, json={"private": True}, timeout=10)
    return {
        "action": "forked",
        "url": new_url,
        "default_branch": default_branch,
        "visibility": _classify_visibility_patch(r4.status_code),
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
