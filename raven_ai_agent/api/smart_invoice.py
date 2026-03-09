"""
Smart Invoice Module — Split from workflows.py
Phase 2: Optimization

Contains invoice-related intelligence:
- Mexico CFDI field resolution (PUE/PPD, G01/G03)
- Invoice creation helpers

These were previously embedded in workflows.py (lines 221-253).
"""
import frappe
from typing import Dict, Optional


# =============================================================================
# MEXICO CFDI FIELD RESOLUTION
# =============================================================================

def resolve_pue_ppd(payment_terms_template: str = None, payment_schedule: list = None) -> str:
    """Determine PUE vs PPD using 3-tier truth hierarchy.
    
    BUG19 fix: Document payment_schedule is GROUND TRUTH — checked FIRST.
    Template name keywords are just labels and can be wrong (e.g. "T/T In Advance"
    with credit_days=30 from migration data).
    
    Truth hierarchy:
    1. DOCUMENT: payment_schedule[].credit_days (ground truth from actual doc)
       - ANY row credit_days > 0 → PPD (credit/deferred)
       - ALL rows credit_days == 0 → PUE (immediate/advance)
    2. TEMPLATE: Payment Terms Template Detail child table credit_days
       - Same logic: any > 0 → PPD, all == 0 → PUE
    3. KEYWORDS: Fallback matching on template name
    4. DEFAULT: PUE (no credit data found anywhere = immediate)
    
    Args:
        payment_terms_template: Name of the Payment Terms Template
        payment_schedule: List of dicts/objects with 'credit_days' from source doc
    
    Returns: 'PUE' or 'PPD'
    """
    # --- TIER 1: Document's own payment_schedule (GROUND TRUTH) ---
    if payment_schedule:
        def _get_credit_days(row):
            if isinstance(row, dict):
                return int(row.get('credit_days', 0) or 0)
            return int(getattr(row, 'credit_days', 0) or 0)
        
        has_credit = any(_get_credit_days(row) > 0 for row in payment_schedule)
        if has_credit:
            return 'PPD'
        else:
            return 'PUE'
    
    # --- TIER 2: Payment Terms Template Detail from DB ---
    if payment_terms_template:
        try:
            template_rows = frappe.get_all(
                'Payment Terms Template Detail',
                filters={'parent': payment_terms_template},
                fields=['credit_days'],
                order_by='idx asc'
            )
            if template_rows:
                max_days = max(int(row.get('credit_days') or 0) for row in template_rows)
                return 'PPD' if max_days > 0 else 'PUE'
        except Exception:
            pass  # Fall through to keywords
    
        # --- TIER 3: Keyword matching on template name ---
        pt_lower = payment_terms_template.lower()
        pue_keywords = ['advance', 'anticipad', 'contado', 'immediate', 'inmediato',
                        'pue', 'prepaid', 'adelant', 'previo', 'antes']
        ppd_keywords = ['days', 'dias', 'credit', 'credito', 'net ', 'parcialidad',
                        'diferido', 'ppd', 'after', 'reception', 'recepcion',
                        'delivery', 'entrega']
        
        if any(kw in pt_lower for kw in pue_keywords):
            return 'PUE'
        elif any(kw in pt_lower for kw in ppd_keywords):
            return 'PPD'
    
    # --- DEFAULT: PUE (no credit data found anywhere = immediate) ---
    return 'PUE'


def resolve_mx_cfdi_fields(customer: str, payment_terms_template: str = None,
                           payment_schedule: list = None) -> Dict:
    """Resolve Mexico CFDI fields for Sales Invoice.
    
    Business rules (BUG19 — 3-tier truth hierarchy):
    - PUE = Pay in advance (Pago en Una sola Exhibicion) — credit_days == 0
    - PPD = Credit terms (Pago en Parcialidades o Diferido) — credit_days > 0
    - Document payment_schedule.credit_days is GROUND TRUTH over template name
    - CFDI Use: G01 for goods, G03 default
    - Mode of Payment: Wire Transfer default
    
    Args:
        customer: Customer name
        payment_terms_template: Payment Terms Template name
        payment_schedule: List of payment_schedule rows from source doc (ground truth)
    """
    result = {
        "mx_payment_option": resolve_pue_ppd(payment_terms_template, payment_schedule),
        "mx_cfdi_use": "G01",
        "mode_of_payment": "Wire Transfer"
    }
    
    # Use cached customer meta if available for CFDI use override
    cust_cfdi = None
    try:
        from raven_ai_agent.api.cache_layer import get_customer_meta
        cust_meta = get_customer_meta(customer)
        if cust_meta:
            cust_cfdi = cust_meta.get("mx_cfdi_use")
    except ImportError:
        cust_cfdi = frappe.db.get_value("Customer", customer, "mx_cfdi_use")
    
    # Override CFDI use from customer record if set
    if cust_cfdi:
        result["mx_cfdi_use"] = cust_cfdi
    
    return result
