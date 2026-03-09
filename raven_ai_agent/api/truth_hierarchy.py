"""
Truth Hierarchy Utility — Shared field resolution for raven_ai_agent
Recommendation R1 from Lessons Learned (March 8, 2026)

The single most important pattern from 19 bugs across 20 QTN tests:
  Document data > Template definitions > Keyword heuristics

This module provides:
- resolve_pue_ppd(): 3-tier PUE/PPD resolution (BUGs 16-19)
- resolve_cfdi_use(): CFDI Use resolution with customer history
- resolve_mode_of_payment(): Payment mode from customer history
- resolve_mx_cfdi_fields(): All-in-one CFDI field resolver
- log_decision(): Audit trail for CFDI-critical decisions (R7)

Usage:
    from raven_ai_agent.api.truth_hierarchy import resolve_mx_cfdi_fields, log_decision
    
    cfdi = resolve_mx_cfdi_fields(source_doc)
    # Returns: {"mx_payment_option": "PPD", "mx_cfdi_use": "G01", 
    #           "mode_of_payment": "Wire Transfer", "_audit": [...]}
"""
import frappe
from typing import Dict, List, Optional, Any
from frappe.utils import nowdate


# =============================================================================
# AUDIT LOGGING (R7)
# =============================================================================

def log_decision(field: str, value: str, tier: int, reason: str, 
                 doc_name: str = None, decisions: list = None) -> Dict:
    """Log a CFDI-critical decision for audit trail.
    
    Args:
        field: Field name (e.g., "mx_payment_option")
        value: Resolved value (e.g., "PPD")
        tier: Which tier resolved it (1=doc, 2=template, 3=keywords, 4=default)
        reason: Human-readable explanation
        doc_name: Source document name for reference
        decisions: Optional list to append to (for batch logging)
    
    Returns:
        Dict with decision details
    """
    tier_labels = {1: "Document", 2: "Template DB", 3: "Keywords", 4: "Default"}
    decision = {
        "field": field,
        "value": value,
        "tier": tier,
        "tier_label": tier_labels.get(tier, f"Tier {tier}"),
        "reason": reason,
        "doc": doc_name or "",
        "timestamp": nowdate()
    }
    if decisions is not None:
        decisions.append(decision)
    
    # Also log to frappe logger for server-side audit
    try:
        frappe.logger("raven_ai_agent").info(
            f"CFDI Decision: {field}={value} | "
            f"Tier {tier} ({tier_labels.get(tier,'?')}) | "
            f"{reason} | doc={doc_name}"
        )
    except Exception:
        pass  # Logging should never break execution
    
    return decision


# =============================================================================
# PUE/PPD RESOLUTION — 3-Tier Truth Hierarchy
# =============================================================================

def resolve_pue_ppd(source_doc=None, payment_terms_template: str = None,
                    payment_schedule: list = None, audit: list = None) -> str:
    """Determine PUE vs PPD using the 3-tier truth hierarchy.
    
    Truth hierarchy (BUG19):
    1. DOCUMENT: source_doc.payment_schedule[].credit_days (ground truth)
       - ANY row credit_days > 0 → PPD
       - ALL rows credit_days == 0 → PUE
    2. TEMPLATE: Payment Terms Template Detail child table from DB
       - Same logic: any > 0 → PPD, all == 0 → PUE
    3. KEYWORDS: Fallback matching on template name
    4. DEFAULT: PUE (no credit data found = immediate payment)
    
    Args:
        source_doc: The source ERPNext document (SO, DN, QTN) — preferred
        payment_terms_template: Template name string (fallback if no doc)
        payment_schedule: Explicit schedule rows (fallback if no doc)
        audit: Optional list to collect audit decisions
    
    Returns: 'PUE' or 'PPD'
    """
    doc_name = getattr(source_doc, 'name', None) if source_doc else None
    
    # --- TIER 1: Document's own payment_schedule (GROUND TRUTH) ---
    schedule = None
    if source_doc:
        schedule = getattr(source_doc, 'payment_schedule', None) or []
    elif payment_schedule:
        schedule = payment_schedule
    
    if schedule:
        max_credit = 0
        for row in schedule:
            if isinstance(row, dict):
                cd = int(row.get('credit_days', 0) or 0)
            else:
                cd = int(getattr(row, 'credit_days', 0) or 0)
            if cd > max_credit:
                max_credit = cd
        
        if max_credit > 0:
            log_decision("mx_payment_option", "PPD", 1,
                        f"doc.payment_schedule has credit_days={max_credit}",
                        doc_name, audit)
            return 'PPD'
        else:
            log_decision("mx_payment_option", "PUE", 1,
                        "doc.payment_schedule ALL credit_days=0",
                        doc_name, audit)
            return 'PUE'
    
    # --- TIER 2: Payment Terms Template Detail from DB ---
    pt_template = payment_terms_template
    if not pt_template and source_doc:
        pt_template = getattr(source_doc, 'payment_terms_template', '') or ''
    
    if pt_template:
        try:
            template_rows = frappe.get_all(
                'Payment Terms Template Detail',
                filters={'parent': pt_template},
                fields=['credit_days'],
                order_by='idx asc'
            )
            if template_rows:
                max_days = max(int(row.get('credit_days') or 0) for row in template_rows)
                if max_days > 0:
                    log_decision("mx_payment_option", "PPD", 2,
                                f"Template '{pt_template}' has credit_days={max_days}",
                                doc_name, audit)
                    return 'PPD'
                else:
                    log_decision("mx_payment_option", "PUE", 2,
                                f"Template '{pt_template}' ALL credit_days=0",
                                doc_name, audit)
                    return 'PUE'
        except Exception:
            pass  # Fall through to keywords
    
        # --- TIER 3: Keyword matching on template name ---
        pt_lower = pt_template.lower()
        pue_keywords = ['advance', 'anticipad', 'contado', 'immediate', 'inmediato',
                        'pue', 'prepaid', 'adelant', 'previo', 'antes']
        ppd_keywords = ['days', 'dias', 'credit', 'credito', 'net ', 'parcialidad',
                        'diferido', 'ppd', 'after', 'reception', 'recepcion',
                        'delivery', 'entrega']
        
        for kw in pue_keywords:
            if kw in pt_lower:
                log_decision("mx_payment_option", "PUE", 3,
                            f"Keyword '{kw}' matched in '{pt_template}'",
                            doc_name, audit)
                return 'PUE'
        for kw in ppd_keywords:
            if kw in pt_lower:
                log_decision("mx_payment_option", "PPD", 3,
                            f"Keyword '{kw}' matched in '{pt_template}'",
                            doc_name, audit)
                return 'PPD'
    
    # --- TIER 4: DEFAULT ---
    log_decision("mx_payment_option", "PUE", 4,
                "No credit data found anywhere — default PUE",
                doc_name, audit)
    return 'PUE'


# =============================================================================
# CFDI USE RESOLUTION
# =============================================================================

def resolve_cfdi_use(source_doc=None, customer: str = None,
                     audit: list = None) -> str:
    """Resolve mx_cfdi_use using truth hierarchy.
    
    Tiers:
    1. Customer record (mx_cfdi_use field)
    2. Customer's last submitted invoice
    3. Default: G01 (goods acquisition)
    """
    doc_name = getattr(source_doc, 'name', None) if source_doc else None
    cust = customer or (getattr(source_doc, 'customer', None) if source_doc else None)
    
    if not cust:
        log_decision("mx_cfdi_use", "G01", 4, "No customer — default G01",
                     doc_name, audit)
        return 'G01'
    
    # Tier 1: Customer record
    try:
        cust_cfdi = frappe.db.get_value("Customer", cust, "mx_cfdi_use")
        if cust_cfdi:
            log_decision("mx_cfdi_use", cust_cfdi, 1,
                        f"Customer record has mx_cfdi_use={cust_cfdi}",
                        doc_name, audit)
            return cust_cfdi
    except Exception:
        pass
    
    # Tier 2: Last submitted invoice
    try:
        last_si = frappe.get_all(
            'Sales Invoice',
            filters={'customer': cust, 'docstatus': 1},
            fields=['mx_cfdi_use'],
            order_by='posting_date desc',
            limit_page_length=1
        )
        if last_si and last_si[0].get('mx_cfdi_use'):
            val = last_si[0]['mx_cfdi_use']
            log_decision("mx_cfdi_use", val, 2,
                        f"Last invoice for {cust} has mx_cfdi_use={val}",
                        doc_name, audit)
            return val
    except Exception:
        pass
    
    # Default
    log_decision("mx_cfdi_use", "G01", 4, "Default G01 (goods)",
                 doc_name, audit)
    return 'G01'


# =============================================================================
# MODE OF PAYMENT RESOLUTION
# =============================================================================

def resolve_mode_of_payment(source_doc=None, customer: str = None,
                            audit: list = None) -> str:
    """Resolve mode_of_payment using truth hierarchy.
    
    Tiers:
    1. Customer's last submitted invoice
    2. Default: Wire Transfer
    """
    doc_name = getattr(source_doc, 'name', None) if source_doc else None
    cust = customer or (getattr(source_doc, 'customer', None) if source_doc else None)
    
    if not cust:
        log_decision("mode_of_payment", "Wire Transfer", 4,
                     "No customer — default Wire Transfer", doc_name, audit)
        return 'Wire Transfer'
    
    # Tier 1: Last submitted invoice
    try:
        last_si = frappe.get_all(
            'Sales Invoice',
            filters={'customer': cust, 'docstatus': 1},
            fields=['mode_of_payment'],
            order_by='posting_date desc',
            limit_page_length=1
        )
        if last_si and last_si[0].get('mode_of_payment'):
            val = last_si[0]['mode_of_payment']
            log_decision("mode_of_payment", val, 2,
                        f"Last invoice for {cust} has mode_of_payment={val}",
                        doc_name, audit)
            return val
    except Exception:
        pass
    
    # Default
    log_decision("mode_of_payment", "Wire Transfer", 4,
                 "Default Wire Transfer", doc_name, audit)
    return 'Wire Transfer'


# =============================================================================
# MASTER RESOLVER — All CFDI fields at once
# =============================================================================

def resolve_mx_cfdi_fields(source_doc=None, customer: str = None,
                           payment_terms_template: str = None,
                           payment_schedule: list = None) -> Dict:
    """Resolve all Mexico CFDI fields using the truth hierarchy.
    
    This is the SINGLE ENTRY POINT for CFDI field resolution (R4).
    Both sales.py and workflow_orchestrator.py should call this.
    
    Args:
        source_doc: The source ERPNext document (preferred — has all data)
        customer: Customer name (fallback if no doc)
        payment_terms_template: Template name (fallback if no doc)
        payment_schedule: Schedule rows (fallback if no doc)
    
    Returns:
        Dict with resolved fields + audit trail:
        {
            "mx_payment_option": "PPD",
            "mx_cfdi_use": "G01",
            "mode_of_payment": "Wire Transfer",
            "_audit": [...]  # List of decision records
        }
    """
    audit = []
    
    result = {
        "mx_payment_option": resolve_pue_ppd(
            source_doc=source_doc,
            payment_terms_template=payment_terms_template,
            payment_schedule=payment_schedule,
            audit=audit
        ),
        "mx_cfdi_use": resolve_cfdi_use(
            source_doc=source_doc,
            customer=customer,
            audit=audit
        ),
        "mode_of_payment": resolve_mode_of_payment(
            source_doc=source_doc,
            customer=customer,
            audit=audit
        ),
        "_audit": audit
    }
    
    return result


# =============================================================================
# IDEMPOTENCY GUARDS (R2)
# =============================================================================

def check_existing_so(quotation_name: str) -> Optional[str]:
    """Check if a Sales Order already exists for this Quotation.
    
    Returns SO name if exists, None otherwise.
    """
    try:
        existing = frappe.db.get_value(
            "Sales Order Item",
            {"prevdoc_docname": quotation_name, "docstatus": ["!=", 2]},
            "parent"
        )
        return existing
    except Exception:
        return None


def check_existing_dn(so_name: str) -> Optional[str]:
    """Check if a Delivery Note already exists for this Sales Order.
    
    Returns DN name if exists (non-cancelled), None otherwise.
    """
    try:
        existing = frappe.get_all(
            "Delivery Note Item",
            filters={"against_sales_order": so_name, "docstatus": ["!=", 2]},
            fields=["parent"],
            limit_page_length=1
        )
        return existing[0]["parent"] if existing else None
    except Exception:
        return None


def check_existing_si(so_name: str = None, dn_name: str = None) -> Optional[str]:
    """Check if a Sales Invoice already exists for this SO or DN.
    
    Returns SI name if exists (non-cancelled), None otherwise.
    """
    try:
        if so_name:
            existing = frappe.get_all(
                "Sales Invoice Item",
                filters={"sales_order": so_name, "docstatus": ["!=", 2]},
                fields=["parent"],
                limit_page_length=1
            )
            if existing:
                return existing[0]["parent"]
        if dn_name:
            existing = frappe.get_all(
                "Sales Invoice Item",
                filters={"delivery_note": dn_name, "docstatus": ["!=", 2]},
                fields=["parent"],
                limit_page_length=1
            )
            if existing:
                return existing[0]["parent"]
    except Exception:
        pass
    return None


# =============================================================================
# PIPELINE VALIDATION (R6)
# =============================================================================

def validate_pipeline(quotation_name: str) -> Dict:
    """Validate the full pipeline for a Quotation.
    
    Checks:
    - QTN is Ordered
    - SO exists and is Submitted
    - DN exists and is Submitted
    - SI exists (Draft or Submitted)
    - CFDI fields are correct
    - Amounts match across documents
    
    Returns:
        Dict with validation results and any issues found.
    """
    issues = []
    results = {
        "quotation": quotation_name,
        "status": "PASS",
        "documents": {},
        "cfdi": {},
        "issues": issues
    }
    
    # 1. Check Quotation
    try:
        qtn = frappe.get_doc("Quotation", quotation_name)
        results["documents"]["quotation"] = {
            "name": qtn.name,
            "status": qtn.status,
            "docstatus": qtn.docstatus,
            "grand_total": qtn.grand_total,
            "currency": qtn.currency,
            "customer": qtn.party_name
        }
        if qtn.status != "Ordered":
            issues.append(f"QTN {qtn.name} status is '{qtn.status}', expected 'Ordered'")
    except Exception as e:
        issues.append(f"Cannot read Quotation: {str(e)}")
        results["status"] = "FAIL"
        return results
    
    # 2. Check Sales Order
    so_name = check_existing_so(quotation_name)
    if not so_name:
        issues.append(f"No Sales Order found for {quotation_name}")
        results["status"] = "FAIL"
        return results
    
    try:
        so = frappe.get_doc("Sales Order", so_name)
        results["documents"]["sales_order"] = {
            "name": so.name,
            "status": so.status,
            "docstatus": so.docstatus,
            "grand_total": so.grand_total,
            "currency": so.currency,
            "payment_terms": so.payment_terms_template
        }
        if so.docstatus != 1:
            issues.append(f"SO {so.name} is not submitted (docstatus={so.docstatus})")
        # Amount check
        if abs(so.grand_total - qtn.grand_total) > 0.01:
            issues.append(
                f"Amount mismatch: QTN={qtn.grand_total} vs SO={so.grand_total}"
            )
    except Exception as e:
        issues.append(f"Cannot read Sales Order: {str(e)}")
        results["status"] = "FAIL"
        return results
    
    # 3. Check Delivery Note
    dn_name = check_existing_dn(so_name)
    if dn_name:
        try:
            dn = frappe.get_doc("Delivery Note", dn_name)
            results["documents"]["delivery_note"] = {
                "name": dn.name,
                "status": dn.status,
                "docstatus": dn.docstatus,
                "grand_total": dn.grand_total
            }
            if dn.docstatus != 1:
                issues.append(f"DN {dn.name} is not submitted (docstatus={dn.docstatus})")
        except Exception as e:
            issues.append(f"Cannot read Delivery Note: {str(e)}")
    else:
        issues.append(f"No Delivery Note found for SO {so_name}")
    
    # 4. Check Sales Invoice
    si_name = check_existing_si(so_name=so_name, dn_name=dn_name)
    if si_name:
        try:
            si = frappe.get_doc("Sales Invoice", si_name)
            results["documents"]["sales_invoice"] = {
                "name": si.name,
                "status": si.status,
                "docstatus": si.docstatus,
                "grand_total": si.grand_total,
                "currency": si.currency
            }
            
            # CFDI validation
            cfdi_expected = resolve_mx_cfdi_fields(source_doc=so)
            results["cfdi"] = {
                "expected_payment_option": cfdi_expected["mx_payment_option"],
                "actual_payment_option": getattr(si, "mx_payment_option", ""),
                "expected_cfdi_use": cfdi_expected["mx_cfdi_use"],
                "actual_cfdi_use": getattr(si, "mx_cfdi_use", ""),
                "audit": [
                    f"{d['tier_label']}: {d['reason']}" 
                    for d in cfdi_expected.get("_audit", [])
                ]
            }
            
            if cfdi_expected["mx_payment_option"] != getattr(si, "mx_payment_option", ""):
                issues.append(
                    f"CFDI mismatch: SI has {si.mx_payment_option}, "
                    f"expected {cfdi_expected['mx_payment_option']} "
                    f"({cfdi_expected['_audit'][0]['reason'] if cfdi_expected.get('_audit') else ''})"
                )
            
            # Amount check
            if abs(si.grand_total - so.grand_total) > 0.01:
                issues.append(
                    f"Amount mismatch: SO={so.grand_total} vs SI={si.grand_total}"
                )
        except Exception as e:
            issues.append(f"Cannot read Sales Invoice: {str(e)}")
    else:
        issues.append(f"No Sales Invoice found for SO {so_name}")
    
    # Final status
    if issues:
        results["status"] = "ISSUES_FOUND"
    
    return results


def format_pipeline_validation(result: Dict) -> str:
    """Format pipeline validation result as a readable message."""
    lines = []
    
    status_emoji = {
        "PASS": "✅",
        "FAIL": "❌",
        "ISSUES_FOUND": "⚠️"
    }
    
    emoji = status_emoji.get(result["status"], "❓")
    lines.append(f"{emoji} **Pipeline Validation: {result['quotation']}**\n")
    
    # Documents
    docs = result.get("documents", {})
    if "quotation" in docs:
        q = docs["quotation"]
        lines.append(f"  📋 QTN: {q['name']} | {q['status']} | {q['currency']} {q['grand_total']:,.2f}")
    if "sales_order" in docs:
        s = docs["sales_order"]
        lines.append(f"  📦 SO: {s['name']} | Status: {s['status']} | Terms: {s.get('payment_terms','N/A')}")
    if "delivery_note" in docs:
        d = docs["delivery_note"]
        lines.append(f"  🚚 DN: {d['name']} | Submitted: {'✅' if d['docstatus'] == 1 else '❌'}")
    if "sales_invoice" in docs:
        i = docs["sales_invoice"]
        lines.append(f"  🧾 SI: {i['name']} | Status: {i['status']} | {i['currency']} {i['grand_total']:,.2f}")
    
    # CFDI
    cfdi = result.get("cfdi", {})
    if cfdi:
        lines.append(f"\n  🇲🇽 CFDI: {cfdi.get('actual_payment_option','?')} (expected: {cfdi.get('expected_payment_option','?')})")
        if cfdi.get("audit"):
            for a in cfdi["audit"][:3]:
                lines.append(f"    └─ {a}")
    
    # Issues
    issues = result.get("issues", [])
    if issues:
        lines.append(f"\n  **Issues ({len(issues)}):**")
        for issue in issues:
            lines.append(f"  ⚠️ {issue}")
    else:
        lines.append(f"\n  **No issues found** ✅")
    
    return "\n".join(lines)
