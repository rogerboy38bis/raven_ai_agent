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

3. Mexico-specific high-risk PII (always-strip):
   - RFC (Mexican tax ID — both Persona Física [13] and Moral [12])
   - CURP (population registry — 18 chars with strict structure)
   - INE clave de elector (18 chars with strict structure)
   - CLABE (18-digit interbank account, requires keyword proximity)
   - NSS / IMSS social-security number (11 digits, requires keyword proximity)
   - Mexico phone numbers (+52 country-code aware)

   These are applied unconditionally because they are high-risk customer PII
   that should never reach a public fork, even when ``strip_pii=False``.

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

# ---- Mexico-specific high-risk PII (always-strip) ------------------------ #
# These are applied unconditionally on every redact() call because they
# encode customer/citizen identity. Order matters — more-specific patterns
# run first so they win the substring race against generic ones.

# A) RFC Persona Física: 4 letters + 6 date digits + 3 alphanumeric (13 chars)
RE_RFC_PERSONA = re.compile(
    r"\b[A-ZÑ&]{4}\d{6}[A-Z0-9]{3}\b",
    re.IGNORECASE,
)

# B) CURP: 18 chars, very strict structure (positions 11=H/M/X, 12-13=state).
RE_CURP = re.compile(
    r"\b[A-Z]{4}\d{6}[HMX][A-Z]{5}[A-Z0-9]\d\b",
    re.IGNORECASE,
)

# C) INE clave de elector: 6 letters + 8 digits + H/M + 3 digits (18 chars).
RE_INE_CLAVE = re.compile(
    r"\b[A-Z]{6}\d{8}[HM]\d{3}\b",
    re.IGNORECASE,
)

# D) RFC Persona Moral: 3 letters + 6 date digits + 3 alphanumeric (12 chars).
# Apply AFTER RE_RFC_PERSONA so we don't eat the first 12 chars of a 13-char
# persona RFC.
RE_RFC_MORAL = re.compile(
    r"\b[A-ZÑ&]{3}\d{6}[A-Z0-9]{3}\b",
    re.IGNORECASE,
)

# E) CLABE — 18 digits, REQUIRES context keyword within 50 chars (either side).
# Bare 18-digit strings could be order numbers, batch IDs, etc., so we only
# redact when a Mexico-bank context keyword is nearby.
_CLABE_CONTEXT = r"(?:\bCLABE\b|\bbanco\b|\bcuenta\s+(?:bancaria|interbancaria)\b)"
RE_CLABE_WITH_CONTEXT = re.compile(
    rf"({_CLABE_CONTEXT}[^\n\r]{{0,50}}?)\b(\d{{18}})\b",
    re.IGNORECASE | re.DOTALL,
)
RE_CLABE_REVERSE = re.compile(
    rf"\b(\d{{18}})\b([^\n\r]{{0,50}}?{_CLABE_CONTEXT})",
    re.IGNORECASE | re.DOTALL,
)

# F) NSS / IMSS — 11 digits, same proximity strategy as CLABE.
_NSS_CONTEXT = (
    r"(?:\bNSS\b|\bIMSS\b|\bISSSTE\b|"
    r"\bn[úu]mero\s+de\s+seguro\s+social\b|"
    r"\bseguro\s+social\b)"
)
RE_NSS_WITH_CONTEXT = re.compile(
    rf"({_NSS_CONTEXT}[^\n\r]{{0,50}}?)\b(\d{{11}})\b",
    re.IGNORECASE | re.DOTALL,
)
RE_NSS_REVERSE = re.compile(
    rf"\b(\d{{11}})\b([^\n\r]{{0,50}}?{_NSS_CONTEXT})",
    re.IGNORECASE | re.DOTALL,
)

# G) Mexico phone — covers +52 with optional area code, separator-bearing
# 10-digit forms, and bare 10-digit numbers. Bounded so 11+ contiguous
# digits (e.g. NSS without context) do NOT get phone-redacted.
# Over-redaction is safer than under-redaction in a bug payload, but we
# still need to leave 11-digit NSS-without-context strings alone.
RE_MX_PHONE = re.compile(
    r"(?:"
    # Form 1: +52 with optional separators and area code (any spacing).
    r"\+?52[\s\-]?(?:\(?\d{2,3}\)?[\s\-]?)?\d{3,4}[\s\-]?\d{4}"
    r"|"
    # Form 2: 10-digit grouped with separators (e.g. 555-123-4567).
    r"\b\d{2,3}[\s\-]\d{3,4}[\s\-]\d{4}\b"
    r"|"
    # Form 3: exactly 10 contiguous digits, not preceded or followed by
    # another digit (so 11-digit strings do not match).
    r"(?<!\d)\d{10}(?!\d)"
    r")"
)

# Ordered list of (pattern, replacement) — applied in sequence.
# Specific Mexico PII patterns FIRST so they precede the generic patterns.
_MX_PII_PATTERNS = [
    (RE_RFC_PERSONA, "[REDACTED:RFC]"),
    (RE_CURP, "[REDACTED:CURP]"),
    (RE_INE_CLAVE, "[REDACTED:INE]"),
    (RE_RFC_MORAL, "[REDACTED:RFC]"),
    # CLABE / NSS substitutions preserve the keyword and surrounding text;
    # only the digit-group is replaced. Handled via lambda below.
]


def _redact_mx_pii(text: str) -> str:
    """Apply Mexico-specific high-risk PII redactions.

    These run unconditionally on every redact() call — they cover identity
    data that should never leave the trusted environment.
    """
    out = text
    for pattern, repl in _MX_PII_PATTERNS:
        out = pattern.sub(repl, out)

    # CLABE: keyword-then-digits
    out = RE_CLABE_WITH_CONTEXT.sub(lambda m: m.group(1) + "[REDACTED:CLABE]", out)
    # CLABE: digits-then-keyword
    out = RE_CLABE_REVERSE.sub(lambda m: "[REDACTED:CLABE]" + m.group(2), out)
    # NSS: keyword-then-digits
    out = RE_NSS_WITH_CONTEXT.sub(lambda m: m.group(1) + "[REDACTED:NSS]", out)
    # NSS: digits-then-keyword
    out = RE_NSS_REVERSE.sub(lambda m: "[REDACTED:NSS]" + m.group(2), out)

    # Mexico phone (also handles bare 10-digit). Applied last so the digit-
    # context patterns (CLABE/NSS) get first crack at their keyword-bearing
    # neighbourhoods.
    out = RE_MX_PHONE.sub("[REDACTED:PHONE]", out)
    return out


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
    """Convenience: always strip secrets + Mexico high-risk PII; optionally
    strip the broader PII set (email / generic phone / generic RFC)."""
    if not text or not isinstance(text, str):
        return text
    out = redact_secrets(text)
    out = _redact_mx_pii(out)
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
