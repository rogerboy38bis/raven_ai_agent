"""
Smart Invoice Module — Split from workflows.py
Phase 2: Optimization

Contains invoice-related intelligence:
- Mexico CFDI field resolution (PUE/PPD, G01/G03)
- Invoice creation helpers

BUG19 completion: Replaced inline 3-tier PUE/PPD logic (~100 lines) with
thin wrappers that delegate to truth_hierarchy.py (R1/R4). This ensures:
- Single source of truth for PUE/PPD, CFDI Use, and mode_of_payment
- R7 audit logging works for callers importing from this module
- Any future fix to truth_hierarchy propagates automatically

Backward compatibility preserved: Other modules that import
  from smart_invoice import resolve_mx_cfdi_fields
still work — the function signature is unchanged.
"""
from typing import Dict, Optional


# =============================================================================
# MEXICO CFDI FIELD RESOLUTION — Delegates to truth_hierarchy (R1/R4)
# =============================================================================

def resolve_pue_ppd(payment_terms_template: str = None, payment_schedule: list = None) -> str:
    """Determine PUE vs PPD — delegates to truth_hierarchy.
    
    Kept for backward compatibility. All logic lives in truth_hierarchy.resolve_pue_ppd().
    """
    from raven_ai_agent.api.truth_hierarchy import resolve_pue_ppd as _resolve
    return _resolve(
        payment_terms_template=payment_terms_template,
        payment_schedule=payment_schedule
    )


def resolve_mx_cfdi_fields(customer: str, payment_terms_template: str = None,
                           payment_schedule: list = None) -> Dict:
    """Resolve Mexico CFDI fields — delegates to truth_hierarchy.
    
    Backward-compatible wrapper. Strips internal _audit key.
    """
    from raven_ai_agent.api.truth_hierarchy import (
        resolve_mx_cfdi_fields as _resolve
    )
    result = _resolve(
        customer=customer,
        payment_terms_template=payment_terms_template,
        payment_schedule=payment_schedule
    )
    # Remove internal _audit key for backward compatibility
    result.pop('_audit', None)
    return result
