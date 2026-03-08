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

def resolve_mx_cfdi_fields(customer: str, payment_terms_template: str = None) -> Dict:
    """Resolve Mexico CFDI fields for Sales Invoice.
    
    Business rules:
    - PUE = Pay in advance (Pago en Una sola Exhibicion)
    - PPD = Credit terms like 30 days (Pago en Parcialidades o Diferido)
    - CFDI Use: G01 for goods, G03 default
    - Mode of Payment: Wire Transfer default
    
    Uses cache for customer metadata lookups.
    """
    result = {
        "mx_payment_option": "PPD",
        "mx_cfdi_use": "G01",
        "mode_of_payment": "Wire Transfer"
    }
    
    pue_keywords = ["advance", "anticipad", "prepaid", "antes", "previo", "adelant"]
    ppd_keywords = ["days", "dias", "credit", "credito", "net ", "after"]
    
    # Build terms string from template name + customer default terms
    terms_str = (payment_terms_template or "").lower()
    
    # Use cached customer meta if available
    try:
        from raven_ai_agent.api.cache_layer import get_customer_meta
        cust_meta = get_customer_meta(customer)
        if cust_meta:
            customer_terms = (cust_meta.get("payment_terms") or "").lower()
            terms_str += " " + customer_terms
            cust_cfdi = cust_meta.get("mx_cfdi_use")
        else:
            cust_cfdi = None
    except ImportError:
        customer_terms = (frappe.db.get_value("Customer", customer, "payment_terms") or "").lower()
        terms_str += " " + customer_terms
        cust_cfdi = frappe.db.get_value("Customer", customer, "mx_cfdi_use")
    
    # Determine PUE vs PPD from terms
    if any(kw in terms_str for kw in pue_keywords):
        result["mx_payment_option"] = "PUE"
    elif any(kw in terms_str for kw in ppd_keywords):
        result["mx_payment_option"] = "PPD"
    
    # Override CFDI use from customer record if set
    if cust_cfdi:
        result["mx_cfdi_use"] = cust_cfdi
    
    return result
