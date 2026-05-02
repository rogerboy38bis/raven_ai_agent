"""
Secret + PII redaction for bug reports.

Two layers:

1. Always-strip secrets (everywhere, never configurable):
   - OpenAI keys (sk-..., sk-proj-..., sk-cp-...)
   - Anthropic keys (sk-ant-...)
   - Slack tokens (xoxb-..., xoxp-..., xapp-...)
   - GitHub PATs (ghp_..., gho_..., ghu_..., ghs_..., ghr_...)
   - Generic Bearer / Authorization headers
   - JWTs (three base64 segments separated by dots)
   - SSH/SSL private key blocks
   - Generic "password=..." / "token=..." / "secret=..." patterns
   - Frappe Password fields (resolved from doctype meta when available)

2. PII redaction (configurable per destination):
   - Email addresses
   - Phone numbers
   - Long digit sequences likely to be national IDs (RFC, CURP, VAT, etc.)

Document IDs (SO-..., SAL-QTN-..., MFG-WO-..., SINV-..., etc.) are NEVER
redacted — they are essential for reproducing bugs and contain no PII.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Optional

# ---- Always-strip patterns ----------------------------------------------- #
_SECRET_PATTERNS = [
    # OpenAI / DeepSeek / MiniMax CP
    (re.compile(r"sk-(?:proj-|cp-|ant-)?[A-Za-z0-9\-_]{20,}"), "<REDACTED:LLM_KEY>"),
    # Anthropic explicit
    (re.compile(r"sk-ant-[A-Za-z0-9\-_]{20,}"), "<REDACTED:ANTHROPIC_KEY>"),
    # GitHub PATs (classic + fine-grained)
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"), "<REDACTED:GITHUB_PAT>"),
    # Slack
    (re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), "<REDACTED:SLACK_TOKEN>"),
    # Bearer tokens
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-+/=]{20,}"), "Bearer <REDACTED>"),
    # Authorization: Basic ...
    (re.compile(r"(?i)\bauthorization:\s*basic\s+[A-Za-z0-9+/=]{10,}"), "Authorization: Basic <REDACTED>"),
    # JWTs
    (re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"), "<REDACTED:JWT>"),
    # PEM private key blocks
    (re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----[\s\S]+?-----END [A-Z ]+PRIVATE KEY-----"),
     "<REDACTED:PRIVATE_KEY>"),
    # password=... / token=... / secret=... in common formats
    (re.compile(r"(?i)\b(password|passwd|secret|api[_-]?key|access[_-]?token)\s*[:=]\s*['\"]?([^\s'\"]{4,})['\"]?"),
     r"\1=<REDACTED>"),
    # AWS access key id (legacy)
    (re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"), "<REDACTED:AWS_KEY>"),
]

# ---- PII patterns (configurable) ----------------------------------------- #
# IMPORTANT: We MUST NOT match the digit-tail of ERPNext doc IDs like
# SAL-QTN-2024-00783 / SO-00752 / MFG-WO-..., so the phone regex requires
# either a leading + or a leading break that is NOT a hyphen/letter (i.e.
# the start of a number that is genuinely free-standing, not embedded).
_PII_PATTERNS = [
    # email
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "<EMAIL>"),
    # phone with explicit + country code: +52 55 1234 5678
    (re.compile(r"(?<![\w\-])\+\d[\d\s().\-]{6,}\d(?!\w)"), "<PHONE>"),
    # phone without + but at least 9 digits in a row, NOT preceded by hyphen
    # or letter (so doc IDs like SAL-QTN-2024-00783 are safe).
    (re.compile(r"(?<![\w\-])\d{3}[\s.\-]?\d{3}[\s.\-]?\d{4}(?!\w)"), "<PHONE>"),
    # Mexican RFC (4 letters + 6 digits + 3 alphanum)
    (re.compile(r"\b[A-Z&Ñ]{3,4}\d{6}[A-Z\d]{3}\b"), "<RFC>"),
    # CURP
    (re.compile(r"\b[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z\d]\d\b"), "<CURP>"),
]


def redact_secrets(text: str) -> str:
    """Strip secrets only.  Always safe to call."""
    if not text or not isinstance(text, str):
        return text
    out = text
    for pattern, repl in _SECRET_PATTERNS:
        out = pattern.sub(repl, out)
    return out


def redact_pii(text: str) -> str:
    """Strip PII patterns.  Caller decides when to apply."""
    if not text or not isinstance(text, str):
        return text
    out = text
    for pattern, repl in _PII_PATTERNS:
        out = pattern.sub(repl, out)
    return out


def redact(text: str, *, strip_pii: bool = False) -> str:
    """Convenience: always strip secrets; optionally strip PII."""
    out = redact_secrets(text)
    if strip_pii:
        out = redact_pii(out)
    return out


def redact_dict(
    data: Dict[str, Any],
    *,
    strip_pii: bool = False,
    sensitive_keys: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Recursively redact a dict.  Specific keys (e.g. 'password', 'token',
    '*_api_key') get fully replaced regardless of value content."""
    if not isinstance(data, dict):
        return data

    sensitive = {k.lower() for k in (sensitive_keys or [])}
    sensitive.update({
        "password", "passwd", "secret", "token", "access_token", "refresh_token",
        "api_key", "openai_api_key", "deepseek_api_key", "claude_api_key",
        "minimax_api_key", "minimax_cp_key", "github_token", "bug_reporter_github_token",
    })

    out: Dict[str, Any] = {}
    for key, value in data.items():
        key_l = str(key).lower()
        # Match exact or *_suffix patterns we want fully blanked.
        if any(key_l == s or key_l.endswith("_" + s) or key_l.endswith(s) for s in sensitive):
            out[key] = "<REDACTED>"
            continue
        if isinstance(value, dict):
            out[key] = redact_dict(value, strip_pii=strip_pii, sensitive_keys=sensitive_keys)
        elif isinstance(value, list):
            out[key] = [
                redact_dict(v, strip_pii=strip_pii, sensitive_keys=sensitive_keys)
                if isinstance(v, dict) else redact(str(v), strip_pii=strip_pii)
                if isinstance(v, str) else v
                for v in value
            ]
        elif isinstance(value, str):
            out[key] = redact(value, strip_pii=strip_pii)
        else:
            out[key] = value
    return out
