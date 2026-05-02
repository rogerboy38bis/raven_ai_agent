"""
GitHub destination — file an issue on the per-app rogerboy38bis fork.

Uses requests directly (no extra deps).  PAT is resolved through the same
``providers._secrets.resolve_secret`` chain we use for LLM keys.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

import frappe

try:
    import requests
    HAVE_REQUESTS = True
except ImportError:  # pragma: no cover
    HAVE_REQUESTS = False


_GITHUB_API = "https://api.github.com"
_DEFAULT_OWNER = "rogerboy38bis"


# ---- config ----- #
def _resolve_token() -> Optional[str]:
    """PAT for the rogerboy38bis namespace."""
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
    except Exception as exc:  # noqa: BLE001
        frappe.logger().debug(f"[bug_reporter] github token resolve failed: {exc}")
        return None


def _resolve_owner() -> str:
    try:
        v = (frappe.conf or {}).get("bug_reporter_github_owner")
        if v:
            return str(v).strip()
        v = frappe.db.get_single_value("AI Agent Settings", "bug_reporter_github_owner")
        if v:
            return str(v).strip()
    except Exception:  # noqa: BLE001
        pass
    return _DEFAULT_OWNER


def _resolve_repo_for_app(app: str) -> str:
    """Return the destination repo for a given app.

    Fallback chain:
      1. AI Agent Settings.bug_reporter_github_repo_map JSON  (per-app override)
      2. site_config.json: bug_reporter_github_repo_map  (per-app override)
      3. <owner>/<app>   (the fork)
      4. <owner>/raven_ai_agent  (the _default fallback)
    """
    owner = _resolve_owner()
    candidates: Dict[str, str] = {}

    # site_config map
    try:
        m = (frappe.conf or {}).get("bug_reporter_github_repo_map") or {}
        if isinstance(m, dict):
            candidates.update({str(k): str(v) for k, v in m.items()})
    except Exception:  # noqa: BLE001
        pass

    # AI Agent Settings map (stored as JSON Long Text)
    try:
        raw = frappe.db.get_single_value("AI Agent Settings", "bug_reporter_github_repo_map")
        if raw:
            m = json.loads(raw)
            if isinstance(m, dict):
                candidates.update({str(k): str(v) for k, v in m.items()})
    except Exception:  # noqa: BLE001
        pass

    if app in candidates:
        return candidates[app]
    if "_default" in candidates:
        return candidates["_default"]

    # Convention: the rogerboy38bis fork keeps the same name as upstream.
    return f"{owner}/{app}"


# ---- public API ----- #
def publish(payload: Dict[str, Any]) -> Optional[str]:
    """Create a GitHub issue on the per-app fork.  Returns the issue URL,
    or None if disabled / not configured / failed."""
    if not HAVE_REQUESTS:
        frappe.logger().warning("[bug_reporter] requests not available; skipping GitHub")
        return None

    token = _resolve_token()
    if not token:
        # Not configured.  Not an error.
        return None

    repo = _resolve_repo_for_app(payload.get("app") or "raven_ai_agent")
    title, body, labels = _build_issue(payload)

    url = f"{_GITHUB_API}/repos/{repo}/issues"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "raven_ai_agent-bug-reporter",
    }
    data = {"title": title, "body": body, "labels": labels}
    try:
        resp = requests.post(url, json=data, headers=headers, timeout=10)
    except Exception as exc:  # noqa: BLE001
        frappe.logger().warning(f"[bug_reporter] github post failed: {exc}")
        return None

    if resp.status_code == 410:
        # Issues are disabled on the fork.  Try _default fallback once.
        fallback = _resolve_repo_for_app("_default")
        if fallback != repo:
            url2 = f"{_GITHUB_API}/repos/{fallback}/issues"
            try:
                resp = requests.post(url2, json=data, headers=headers, timeout=10)
            except Exception as exc:  # noqa: BLE001
                frappe.logger().warning(f"[bug_reporter] github fallback post failed: {exc}")
                return None

    if not (200 <= resp.status_code < 300):
        frappe.logger().warning(
            f"[bug_reporter] github issue create returned {resp.status_code}: "
            f"{resp.text[:300]}"
        )
        return None

    try:
        return resp.json().get("html_url")
    except Exception:  # noqa: BLE001
        return None


# ---- formatting ---- #
def _build_issue(payload: Dict[str, Any]) -> tuple[str, str, list[str]]:
    fp = payload.get("fp")
    env = payload.get("env")
    bot = payload.get("bot") or "?"
    intent = payload.get("intent") or "?"
    sev = payload.get("severity") or "Medium"
    cls = payload.get("failure_class") or "exception"
    exc = payload.get("exception") or {}

    title = f"[{env}][bug:{fp}] {bot}/{intent} — {(exc.get('type') or cls)}"[:200]

    body_parts = [
        "## Auto-detected by raven_ai_agent.bug_reporter",
        "",
        f"- **Fingerprint:** `{fp}`",
        f"- **Environment:** `{env}`",
        f"- **App:** `{payload.get('app')}`",
        f"- **Severity:** **{sev}**",
        f"- **Bot:** `{bot}`",
        f"- **Intent:** `{intent}`",
        f"- **User:** `{payload.get('user') or '?'}`",
        f"- **Failure class:** `{cls}`",
        "",
        "### Query",
        "```",
        (payload.get("query") or "")[:2000],
        "```",
    ]

    if exc.get("type"):
        body_parts += [
            "",
            f"### Exception: `{exc.get('type')}`",
            f"_module_: `{exc.get('module')}` — _file_: `{exc.get('file')}:{exc.get('line')}`",
            "",
            "**Message**",
            "",
            "```",
            (exc.get("message") or "")[:1500],
            "```",
            "",
            "**Traceback**",
            "",
            "```",
            (exc.get("traceback") or "")[:6000],
            "```",
        ]

    if payload.get("result_text"):
        body_parts += [
            "",
            "### Result text",
            "```",
            payload["result_text"][:2000],
            "```",
        ]

    if payload.get("supervisor_meta"):
        body_parts += [
            "",
            "### Supervisor telemetry",
            "```json",
            json.dumps(payload["supervisor_meta"], indent=2, default=str)[:2000],
            "```",
        ]

    body_parts += [
        "",
        "---",
        "",
        "### Reproduction & fix discipline",
        "",
        "**Mandatory:** bug-fix work happens on a dedicated branch on this fork "
        "(e.g. `bug/" + str(fp) + "`), never on `main`. The fork's `main` must "
        "stay in sync with upstream `rogerboy38/<app>`. Open a PR back to "
        "upstream once the fix is verified.",
    ]

    labels = [f"bug:auto-detected", f"sev:{sev.lower()}", f"env:{env}", f"bot:{bot}"]
    return title, "\n".join(body_parts), labels
