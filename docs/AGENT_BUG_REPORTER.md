# Raven Agent Bug Reporter

Auto-detect and triage agent failures across every environment, file them
in three places (Frappe Error Log, Help Desk ticket, GitHub issue on a
private fork) with deduplication, secret redaction, severity-aware
escalation, and auto-pause of bot autonomy on repeat failures.

## Why

Sample-request and `coa_amb` style intermittent bugs were causing manual
postmortem cycles. The bug reporter turns every silent failure into an
actionable, reproducible record before anyone has to look for it.

## Architecture

```
raven_ai_agent/bug_reporter/
├── __init__.py            # public API: capture()
├── collector.py           # capture(), env tag, payload build, redaction
├── fingerprint.py         # stable 8-hex dedup hash
├── redactor.py            # secret + PII patterns
├── tasks.py               # async worker: upsert + dedup + alarms
├── setup.py               # bootstrap_forks() one-time helper
└── destinations/
    ├── helpdesk.py        # auto-detect HD Ticket → Issue → none
    └── github.py          # POST /repos/<fork>/issues
```

## Capture flow

```
@ai message
   ↓ router.handle_raven_message
   ↓ ───────────────► except Exception          → capture(severity=High)
   ↓ ───────────────► result.success == False   → capture(severity=Medium)
   ↓ supervise()
   ↓ ───────────────► Guardrails High under autonomy=agent → capture(severity=High)
   ↓ ───────────────► Reflection rejected after max_iters  → capture(severity=Medium)
```

`capture()` runs **synchronously** but cheaply: redacts secrets, computes
the fingerprint, calls `frappe.log_error()`, then enqueues the rest via
`frappe.enqueue(..., queue='short', enqueue_after_commit=True)`.

The async worker:
1. Upserts a `Raven Agent Bug` keyed by fingerprint.
2. Deduplicates: within `bug_reporter_dedup_window_hours` (default 24h)
   the existing record gets a new `Raven Agent Bug Occurrence` row and
   `occurrence_count++`. **No** new HD Ticket / GitHub issue is created.
3. Outside the window or on first occurrence: creates HD Ticket (or Issue
   fallback) and GitHub issue, cross-links both.
4. Auto-pause: if a bot accumulates `bug_reporter_autopause_threshold`
   High bugs in `bug_reporter_autopause_window_minutes`, autonomy is
   downgraded to Copilot for that bot until manually acknowledged.
5. Escalation: a scheduler job runs every 5 min and escalates paused bugs
   through Alarm 1 / 2 / 3 timers.

## Configuration

All settings can be set in `site_config.json` (recommended for ops) or in
`AI Agent Settings` (recommended for end-user toggles).

| Key | Default | Purpose |
| --- | --- | --- |
| `bug_reporter_enabled` | unset (off) | Master switch. Env override: `RAVEN_BUG_REPORTER=1`. |
| `bug_reporter_environment` | heuristic | Tag added to every bug: `local`, `server-sandbox`, `test`, `prod`. Env override: `RAVEN_ENV`. |
| `bug_reporter_github_token` | (none) | PAT for `rogerboy38bis`. Encrypted in DB or stored in `site_config.json`. |
| `bug_reporter_github_owner` | `rogerboy38bis` | Owner namespace for forks. |
| `bug_reporter_github_upstream_owner` | `rogerboy38` | Upstream owner used by `bootstrap_forks`. |
| `bug_reporter_github_repo_map` | `{}` | JSON map `{app: "owner/repo"}` for per-app overrides. Includes `_default` fallback. |
| `bug_reporter_dedup_window_hours` | 24 | Within this window, recurrences just bump count. |
| `bug_reporter_autopause_enabled` | 1 | Master switch for auto-pause. |
| `bug_reporter_autopause_threshold` | 5 | High bugs in window before pause. |
| `bug_reporter_autopause_window_minutes` | 60 | Sliding window for the threshold. |
| `bug_reporter_escalation_alarm1_minutes` | 15 | Alarm 1 fires this many minutes after pause. |
| `bug_reporter_escalation_alarm2_minutes` | 30 | Alarm 2 fires. |
| `bug_reporter_escalation_alarm3_minutes` | 45 | Alarm 3 fires (escalation upstairs). |
| `bug_reporter_alarm1_users` | (empty) | Comma-separated emails for Alarm 1. |
| `bug_reporter_alarm2_users` | (empty) | Comma-separated emails for Alarm 2. |
| `bug_reporter_alarm3_users` | (empty) | Comma-separated emails for Alarm 3. |
| `bug_reporter_redact_pii_on_github` | 0 (off) | When **on**, strip emails/phones/RFC/CURP from GitHub payload. Default off because rogerboy38bis is private. |

## Per-environment setup

The PAT and env tag must be set on **each** of your environments (local
sandbox, server sandbox, server test docker, production docker). The
fingerprint is the same across environments, so deduplication works
globally — but the `[env:...]` tag on each issue lets you filter.

### 1. Local sandbox (`frappe@UbuntuVM`, direct bench)

```bash
cd ~/frappe-bench
bench --site sandbox.sysmayal.cloud set-config -p bug_reporter_github_token "ghp_PASTE_PAT"
bench --site sandbox.sysmayal.cloud set-config bug_reporter_github_owner "rogerboy38bis"
bench --site sandbox.sysmayal.cloud set-config bug_reporter_environment "local"
bench --site sandbox.sysmayal.cloud set-config bug_reporter_enabled 1
sudo supervisorctl restart frappe-bench-web: frappe-bench-workers:
```

### 2. Server sandbox (`frappe@sysmayal`, direct bench)

```bash
cd ~/frappe-bench
bench --site sandbox.sysmayal.cloud set-config -p bug_reporter_github_token "ghp_PASTE_PAT"
bench --site sandbox.sysmayal.cloud set-config bug_reporter_github_owner "rogerboy38bis"
bench --site sandbox.sysmayal.cloud set-config bug_reporter_environment "server-sandbox"
bench --site sandbox.sysmayal.cloud set-config bug_reporter_enabled 1
sudo supervisorctl restart frappe-bench-web: frappe-bench-workers:
```

### 3. Server test (Docker, `root@sysmayal`)

```bash
docker exec -it -u frappe erpnext-test-backend-1 bash
# inside the container:
cd ~/frappe-bench
bench --site <test-site> set-config -p bug_reporter_github_token "ghp_PASTE_PAT"
bench --site <test-site> set-config bug_reporter_github_owner "rogerboy38bis"
bench --site <test-site> set-config bug_reporter_environment "test"
bench --site <test-site> set-config bug_reporter_enabled 1
exit
# back on host:
docker restart erpnext-test-backend-1 erpnext-test-queue-short-1 \
                erpnext-test-queue-long-1 erpnext-test-scheduler-1
```

### 4. Production (Docker, `root@srv1415373`)

```bash
docker exec -it -u frappe erpnext-backend-1 bash
# inside the container:
cd ~/frappe-bench
bench --site <prod-site> set-config -p bug_reporter_github_token "ghp_PASTE_PAT"
bench --site <prod-site> set-config bug_reporter_github_owner "rogerboy38bis"
bench --site <prod-site> set-config bug_reporter_environment "prod"
bench --site <prod-site> set-config bug_reporter_enabled 1
exit
# back on host:
docker restart erpnext-backend-1 erpnext-queue-short erpnext-queue-long erpnext-scheduler
```

## One-time fork bootstrap

After the PAT is configured on at least one environment (your local
sandbox is fine), run **once** from any bench:

```bash
bench --site sandbox.sysmayal.cloud execute \
    raven_ai_agent.bug_reporter.setup.bootstrap_forks
```

This creates `rogerboy38bis/<app>` for each of `raven_ai_agent`,
`amb_w_spc`, `amb_w_tds`, `amb_print` (private forks of the upstreams),
and flips visibility to private. Idempotent — safe to re-run.

## Fork discipline (mandatory)

> **GitHub forks can become noisy because by default the fork inherits
> all upstream branches and tags. Bug-fix work happens on dedicated
> branches like `bug/<fingerprint8>` on the fork, never on `main` of the
> fork (which must stay in sync with upstream).**

This applies to all `rogerboy38bis/<app>` forks. Workflow:

1. A bug shows up as a GitHub issue on `rogerboy38bis/<app>` with title
   prefix `[env:...][bug:<fingerprint8>]`.
2. Developer creates a branch on the fork: `bug/<fingerprint8>`.
3. Reproduces, fixes, commits, pushes.
4. Opens a PR from `rogerboy38bis:bug/<fingerprint8>` →
   `rogerboy38:main`.
5. After merge, deletes the bug branch on the fork. Fork's `main` is
   re-synced from upstream so it stays clean.

The reporter's auto-generated GitHub issue body includes this discipline
note as a reminder.

## Tests

```bash
cd ~/frappe-bench/apps/raven_ai_agent
PYTHONPATH=. python3 raven_ai_agent/bug_reporter/tests/test_bug_reporter.py
# All bug reporter smoke tests passed.
```

13 tests cover: secret redaction (OpenAI / GitHub PAT / Bearer / JWT),
PII redaction (email / phone / RFC / CURP), doc-ID preservation,
password-key blanking, fingerprint stability across doc IDs, divergence
on bot/failure-class, capture passthrough when disabled, and full
capture flow with secret stripping.

## Frappe-native integration

- `frappe.log_error` — every bug always lands in the standard Error Log
  with `reference_doctype="Raven Agent Bug"`, so it shows up next to all
  other Frappe errors.
- `Raven Agent Bug.clear_old_logs(days)` static method — auto-registers
  the doctype with **Log Settings** for retention management (default
  180 days).
- `frappe.enqueue(queue='short', enqueue_after_commit=True, job_name=...)` —
  async fire-and-forget after DB commit; deduplicated by job_name within
  the same tick.
- `override_doctype_class` in `hooks.py` — protects `Raven Agent Bug`
  and `Raven Agent Bug Occurrence` from accidental orphan deletion
  during `bench migrate` (same protection AI Memory and AI Agent
  Settings already have).
- `scheduler_events.cron['*/5 * * * *']` — escalation timer.

## Manual operations

```python
# Acknowledge a paused bug from bench console:
import frappe
frappe.get_doc("Raven Agent Bug", "<fingerprint>").run_method("acknowledge")

# Or from the desk: open the Raven Agent Bug record → click Acknowledge button.

# Force-disable globally:
bench --site <site> set-config bug_reporter_enabled 0
sudo supervisorctl restart frappe-bench-web: frappe-bench-workers:
```

## PII redaction — Mexico-specific patterns

The bug reporter pushes redacted payloads to **public** forks under
`github.com/rogerboy38bis/<app>`. Because the operators run Frappe / ERPNext
for Mexican customers, any payload may contain customer identity numbers,
bank accounts, or tax IDs. The redactor (`raven_ai_agent/bug_reporter/redactor.py`)
applies the patterns below **unconditionally** on every `redact()` call —
they are not gated by the `strip_pii` flag.

### Patterns covered

| Pattern         | Format                                                                     | Replacement         |
|-----------------|----------------------------------------------------------------------------|---------------------|
| RFC Persona     | 4 letters + 6 date digits + 3 alphanumeric (13 chars)                      | `[REDACTED:RFC]`    |
| RFC Moral       | 3 letters + 6 date digits + 3 alphanumeric (12 chars)                      | `[REDACTED:RFC]`    |
| CURP            | 4 letters + 6 digits + H/M/X + 5 letters + 1 alphanumeric + 1 digit (18)   | `[REDACTED:CURP]`   |
| INE clave       | 6 letters + 8 digits + H/M + 3 digits (18 chars)                           | `[REDACTED:INE]`    |
| CLABE           | 18 digits + nearby keyword (`CLABE`, `banco`, `cuenta bancaria`, …)        | `[REDACTED:CLABE]`  |
| NSS / IMSS      | 11 digits + nearby keyword (`NSS`, `IMSS`, `ISSSTE`, `seguro social`, …)   | `[REDACTED:NSS]`    |
| Mexico phone    | `+52 …`, separator-grouped 10-digit, or bare 10-digit                      | `[REDACTED:PHONE]`  |

RFC Persona is applied **before** RFC Moral so the moral (12-char) regex
does not eat the first 12 characters of a 13-char persona RFC. CURP and
INE share the same 18-char length but are disambiguated by their strict
internal structure (CURP has `H/M/X` at position 11; INE has `H/M` at
position 15).

### The proximity-keyword strategy (CLABE and NSS)

Bare 18-digit and 11-digit strings appear naturally in production data
as order numbers, batch IDs, tracking codes, etc. Redacting every such
string would destroy debugging signal. So CLABE and NSS only redact
when a Mexico-finance / social-security keyword appears within ~50
characters on either side of the digits:

- CLABE keywords: `CLABE`, `banco`, `cuenta bancaria`, `cuenta interbancaria`
- NSS keywords: `NSS`, `IMSS`, `ISSSTE`, `número de seguro social`, `seguro social`

When the keyword is present, **only the digit group** is replaced; the
keyword and surrounding text are preserved so the bug context still
reads naturally (e.g. `cuenta bancaria [REDACTED:CLABE]`).

### Defense-in-depth, not a guarantee

The redactor is one layer in the bug-publishing pipeline — fixtures and
payload diffs should still be **reviewed by an operator before merge**.
Regex-based redaction can never catch every shape of PII (custom string
formats, partial digits, transliterations, spelling variants), so a
human eye on the public-fork PR is still the last gate.

### CI guard fixture

`raven_ai_agent/bug_reporter/tests/fixtures/synthetic_mexico_pii.txt`
contains deterministically-fabricated examples of every supported
pattern. The unit test
`test_redact_synthetic_pii_fixture_fully_redacted` loads the fixture
and asserts that **none** of those tokens survive `redact()`. If you
extend the redactor with new patterns, add a representative example to
that fixture and a forbidden substring to the test — the CI guard will
fail loudly the moment a new pattern regresses.


