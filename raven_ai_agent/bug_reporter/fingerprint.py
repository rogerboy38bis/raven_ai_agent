"""
Stable bug fingerprint for deduplication.

Goals:
  - same fingerprint when the same bug recurs (so we group occurrences)
  - different fingerprint when something materially changes (different bot,
    different intent, different exception type / module)
  - never include personal data, document IDs, or timestamps in the input

Returned as the first 8 hex chars of sha1 — short, URL-safe, plenty of
entropy for our scale (millions of unique bugs would still rarely collide).
"""
from __future__ import annotations

import hashlib
import re
from typing import Optional


_NORM_DOC_ID = re.compile(
    r"\b(SAL-QTN|SO|MFG-WO|ACC-SINV|SINV|ACC-PAY|PE|DN|PO|MAT-MR|BOM|QA-NC|QA-MEET)-[\w\-/.]+",
    re.IGNORECASE,
)
_NORM_NUMBERS = re.compile(r"\b\d{2,}\b")
_NORM_WS = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """Strip volatile bits so similar errors collapse to the same fingerprint."""
    if not text:
        return ""
    # Replace doc IDs by their family name to group "all SO-* errors" together.
    out = _NORM_DOC_ID.sub(lambda m: m.group(1).upper() + "-X", text)
    # Replace long numeric sequences with N to ignore counters / IDs.
    out = _NORM_NUMBERS.sub("N", out)
    # Collapse whitespace.
    out = _NORM_WS.sub(" ", out).strip().lower()
    return out


def fingerprint(
    *,
    bot: Optional[str],
    intent: Optional[str],
    exception_type: Optional[str] = None,
    exception_module: Optional[str] = None,
    error_summary: Optional[str] = None,
    failure_class: Optional[str] = None,
) -> str:
    """Compute the dedup fingerprint.

    failure_class is a discriminator like "exception", "result_failure",
    "guardrail_block", "reflection_rejected", "provider_chain_exhausted".
    """
    parts = [
        (bot or "_default").strip().lower(),
        (intent or "_unknown").strip().lower(),
        (failure_class or "exception").strip().lower(),
        (exception_module or "").strip().lower(),
        (exception_type or "").strip().lower(),
        _normalize(error_summary or "")[:240],
    ]
    blob = "|".join(parts)
    return hashlib.sha1(blob.encode("utf-8", "replace")).hexdigest()[:8]
