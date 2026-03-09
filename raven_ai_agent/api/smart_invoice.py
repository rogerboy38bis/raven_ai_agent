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

def resolve_pue_ppd(payment_terms_template: str = None) -> str:
    """Determine PUE vs PPD by reading the Payment Terms Template schedule.
    
    Smart logic (BUG16+BUG17 fix):
    1. PRIMARY: Read the Payment Terms Template's payment_schedule child rows.
       - If ALL rows have credit_days == 0 → PUE (immediate/advance payment)
       - If ANY row has credit_days > 0 → PPD (credit/deferred)
    2. FALLBACK: If template not found or DB error, use keyword matching on name.
    3. DEFAULT: PPD (safer — allows payment complement).
    
    This correctly handles cases like "45 DAYS NET CASH" (credit_days=45 → PPD)
    and "T/T After Reception of the goods" (credit_days=100 → PPD) that keyword
    matching alone would misclassify.
    
    Returns: 'PUE' or 'PPD'
    """
    if not payment_terms_template:
        return 'PPD'
    
    # --- PRIMARY: Read actual credit_days from payment_schedule ---
    try:
        schedule_rows = frappe.get_all(
            'Payment Terms Template Detail',
            filters={'parent': payment_terms_template},
            fields=['credit_days'],
            order_by='idx asc'
        )
        if schedule_rows:
            max_days = max(int(row.get('credit_days') or 0) for row in schedule_rows)
            if max_days == 0:
                return 'PUE'
            else:
                return 'PPD'
    except Exception:
        pass  # Fall through to keyword matching
    
    # --- FALLBACK: Keyword matching on template name ---
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
    
    return 'PPD'


def resolve_mx_cfdi_fields(customer: str, payment_terms_template: str = None) -> Dict:
    """Resolve Mexico CFDI fields for Sales Invoice.
    
    Business rules:
    - PUE = Pay in advance (Pago en Una sola Exhibicion) — credit_days == 0
    - PPD = Credit terms (Pago en Parcialidades o Diferido) — credit_days > 0
    - CFDI Use: G01 for goods, G03 default
    - Mode of Payment: Wire Transfer default
    
    Uses Payment Terms Template schedule data for PUE/PPD (not just keywords).
    Uses cache for customer metadata lookups.
    """
    result = {
        "mx_payment_option": resolve_pue_ppd(payment_terms_template),
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
