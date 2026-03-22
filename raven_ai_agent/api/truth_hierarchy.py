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
from raven_ai_agent.utils.doc_resolver import resolve_document_name


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
    tier_labels = {0: "QTN Traceback", 1: "Document", 2: "Template DB", 3: "Keywords", 4: "Default"}
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

def _get_max_credit_days(schedule) -> int:
    """Extract max credit_days from a payment_schedule list.
    
    Handles both frappe Document rows and plain dicts.
    Returns 0 if schedule is empty or all credit_days are 0.
    """
    if not schedule:
        return 0
    max_cd = 0
    for row in schedule:
        if isinstance(row, dict):
            cd = int(row.get('credit_days', 0) or 0)
        else:
            cd = int(getattr(row, 'credit_days', 0) or 0)
        if cd > max_cd:
            max_cd = cd
    return max_cd


def _trace_source_quotation(source_doc) -> 'Optional[object]':
    """Walk back from SO/DN/SI to find the source Quotation.
    
    BUG 22: The Quotation payment_schedule has human-reviewed credit_days
    that may differ from the Payment Terms Template definition. ERPNext's
    make_sales_order() can regenerate payment_schedule from template,
    overwriting the human override. We must read from the QTN.
    
    Returns the Quotation doc if found, None otherwise.
    """
    if not source_doc:
        return None
    
    doctype = getattr(source_doc, 'doctype', '')
    
    try:
        if doctype == 'Quotation':
            return source_doc  # Already a QTN
        
        if doctype == 'Sales Order':
            # SO items have prevdoc_docname pointing to QTN
            items = getattr(source_doc, 'items', []) or []
            for item in items:
                qtn_name = getattr(item, 'prevdoc_docname', None)
                if qtn_name:
                    return frappe.get_doc('Quotation', qtn_name)
        
        if doctype == 'Delivery Note':
            # DN items have against_sales_order → then trace to QTN
            items = getattr(source_doc, 'items', []) or []
            for item in items:
                so_name = getattr(item, 'against_sales_order', None)
                if so_name:
                    so = frappe.get_doc('Sales Order', so_name)
                    return _trace_source_quotation(so)
        
        if doctype == 'Sales Invoice':
            # SI items have sales_order → then trace to QTN
            items = getattr(source_doc, 'items', []) or []
            for item in items:
                so_name = getattr(item, 'sales_order', None)
                if so_name:
                    so = frappe.get_doc('Sales Order', so_name)
                    return _trace_source_quotation(so)
    except Exception:
        pass  # Tracing is best-effort; fall through to other tiers
    
    return None


def resolve_pue_ppd(source_doc=None, payment_terms_template: str = None,
                    payment_schedule: list = None, audit: list = None) -> str:
    """Determine PUE vs PPD using the 5-tier truth hierarchy.
    
    BUG 22 fix: Added Tier 0 — trace back to source Quotation.
    The Quotation payment_schedule has human-reviewed credit_days that
    override template definitions. ERPNext's make_sales_order() can
    regenerate payment_schedule from template, losing the human override.
    
    Truth hierarchy (BUG19 + BUG22):
    0. QUOTATION: Trace source_doc back to its linked Quotation.
       Read QTN.payment_schedule[].credit_days (human-reviewed truth).
       - ANY row credit_days > 0 → PPD
       - ALL rows credit_days == 0 → continue to Tier 1
    1. DOCUMENT: source_doc.payment_schedule[].credit_days
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
    
    # --- TIER 0: Source Quotation (HUMAN-REVIEWED TRUTH) ---
    # BUG 22: Walk back to QTN. The QTN payment_schedule has credit_days
    # set by the human reviewer. This overrides everything.
    if source_doc:
        qtn = _trace_source_quotation(source_doc)
        if qtn and getattr(qtn, 'doctype', '') == 'Quotation':
            qtn_schedule = getattr(qtn, 'payment_schedule', None) or []
            if qtn_schedule:
                qtn_max_cd = _get_max_credit_days(qtn_schedule)
                if qtn_max_cd > 0:
                    log_decision("mx_payment_option", "PPD", 0,
                                f"Source QTN {qtn.name} payment_schedule has credit_days={qtn_max_cd}",
                                doc_name, audit)
                    return 'PPD'
                # QTN has schedule but all credit_days=0 → PUE from QTN
                log_decision("mx_payment_option", "PUE", 0,
                            f"Source QTN {qtn.name} payment_schedule ALL credit_days=0",
                            doc_name, audit)
                return 'PUE'
    
    # --- TIER 1: Document's own payment_schedule ---
    schedule = None
    if source_doc:
        schedule = getattr(source_doc, 'payment_schedule', None) or []
    elif payment_schedule:
        schedule = payment_schedule
    
    if schedule:
        max_credit = _get_max_credit_days(schedule)
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
    
    # Resolve partial/misspelled quotation names
    resolved_qtn = resolve_document_name("Quotation", quotation_name)
    if not resolved_qtn:
        results = {
            "quotation": quotation_name,
            "status": "FAIL",
            "documents": {},
            "cfdi": {},
            "issues": [f"Quotation '{quotation_name}' not found"]
        }
        return results
    
    results = {
        "quotation": resolved_qtn,
        "status": "PASS",
        "documents": {},
        "cfdi": {},
        "issues": issues
    }
    
    # 1. Check Quotation
    try:
        qtn = frappe.get_doc("Quotation", resolved_qtn)
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
    so_name = check_existing_so(resolved_qtn)
    if not so_name:
        issues.append(f"No Sales Order found for {resolved_qtn}")
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
            
            # CFDI validation — passes SO as source_doc.
            # Tier 0 inside resolve_pue_ppd() will trace SO→QTN automatically.
            cfdi_expected = resolve_mx_cfdi_fields(source_doc=so)
            
            # BUG 22: Include QTN credit_days reference in audit output
            qtn_credit_info = ""
            try:
                qtn_sched = getattr(qtn, 'payment_schedule', []) or []
                if qtn_sched:
                    qtn_max_cd = _get_max_credit_days(qtn_sched)
                    qtn_credit_info = f"QTN {qtn.name} credit_days={qtn_max_cd}"
            except Exception:
                pass
            
            results["cfdi"] = {
                "expected_payment_option": cfdi_expected["mx_payment_option"],
                "actual_payment_option": getattr(si, "mx_payment_option", ""),
                "expected_cfdi_use": cfdi_expected["mx_cfdi_use"],
                "actual_cfdi_use": getattr(si, "mx_cfdi_use", ""),
                "qtn_credit_days": qtn_credit_info,
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
    from urllib.parse import quote
    
    lines = []
    
    # Get site URL for links
    site = frappe.local.site
    base_url = f"/desk"
    
    def make_link(doctype: str, docname: str) -> str:
        """Create ERPNext link for a document."""
        # URL encode the docname to handle special characters
        from urllib.parse import quote
        encoded_name = quote(docname, safe='')
        return f"[{docname}]({base_url}/{doctype}/{encoded_name})"
    
    status_emoji = {
        "PASS": "✅",
        "FAIL": "❌",
        "ISSUES_FOUND": "⚠️"
    }
    
    emoji = status_emoji.get(result["status"], "❓")
    qtn_name = result["quotation"]
    lines.append(f"{emoji} **Pipeline Validation:** {make_link('Quotation', qtn_name)}")
    lines.append("")  # Blank line after header
    
    # Documents - each on its own line with clear separation
    docs = result.get("documents", {})
    if "quotation" in docs:
        q = docs["quotation"]
        q_link = make_link("Quotation", q['name'])
        lines.append(f"📋 **QTN:** {q_link} | {q['status']} | {q['currency']} {q['grand_total']:,.2f}")
    if "sales_order" in docs:
        s = docs["sales_order"]
        so_link = make_link("Sales Order", s['name'])
        lines.append(f"📦 **SO:** {so_link} | Status: {s['status']} | Terms: {s.get('payment_terms','N/A')}")
    if "delivery_note" in docs:
        d = docs["delivery_note"]
        dn_link = make_link("Delivery Note", d['name'])
        lines.append(f"🚚 **DN:** {dn_link} | Submitted: {'✅' if d['docstatus'] == 1 else '❌'}")
    if "sales_invoice" in docs:
        i = docs["sales_invoice"]
        si_link = make_link("Sales Invoice", i['name'])
        lines.append(f"🧾 **SI:** {si_link} | Status: {i['status']} | {i['currency']} {i['grand_total']:,.2f}")
    
    lines.append("")  # Blank line before CFDI section
    
    # CFDI
    cfdi = result.get("cfdi", {})
    if cfdi:
        lines.append(f"🇲🇽 **CFDI:** {cfdi.get('actual_payment_option','?')} (expected: {cfdi.get('expected_payment_option','?')})")
        # BUG 22: Show QTN credit_days reference for traceability
        if cfdi.get("qtn_credit_days"):
            lines.append(f"  📎 {cfdi['qtn_credit_days']}")
        if cfdi.get("audit"):
            for a in cfdi["audit"][:3]:
                lines.append(f"  └─ {a}")
    
    lines.append("")  # Blank line before Issues
    
    # Issues
    issues = result.get("issues", [])
    if issues:
        lines.append(f"**Issues ({len(issues)}):**")
        for issue in issues:
            lines.append(f"⚠️ {issue}")
    else:
        lines.append(f"**No issues found** ✅")
    
    return "<br>".join(lines)



# =============================================================================
# ANTI-HALLUCINATION GUARD (Phase 8A)
# =============================================================================

import re
from typing import Dict, List, Optional


def extract_numeric_values(text: str) -> List[Dict]:
    """Extract all numeric values from response text.
    
    Returns list of dicts with: {value, type, position}
    Types: currency, quantity, percentage, date, generic
    """
    results = []
    
    # Currency patterns (various formats)
    currency_patterns = [
        r'\$\s*[\d,]+\.?\d*',           # $1,234.56
        r'[\d,]+\.?\d*\s*(?:USD|EUR|MXN)',  # 1234.56 USD
        r'\$\s*[\d,]+\.?\d*',           # $1234
        r'(?:total|amount|grand_total|subtotal|balance)\s*[:\-]?\s*\$?\s*[\d,]+\.?\d*',
    ]
    
    # Quantity patterns
    quantity_patterns = [
        r'(\d+)\s*(?:units?|pcs?|pieces?|items?|kg|lbs?|boxes?|palettes?)',
        r'qty[:\-]?\s*(\d+)',
        r'quantity[:\-]?\s*(\d+)',
    ]
    
    # Percentage patterns
    percent_patterns = [
        r'(\d+(?:\.\d+)?)\s*%',
        r'(\d+(?:\.\d+)?)\s*percent',
    ]
    
    # Date patterns
    date_patterns = [
        r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
        r'\d{2}/\d{2}/\d{4}',  # MM/DD/YYYY
        r'\d{2}-\d{2}-\d{4}',  # DD-MM-YYYY
    ]
    
    # Extract currencies
    for pattern in currency_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            val_str = re.sub(r'[^\d.]', '', match.group())
            try:
                value = float(val_str)
                if value > 0:
                    results.append({
                        "value": value,
                        "type": "currency",
                        "original": match.group(),
                        "position": match.start()
                    })
            except ValueError:
                pass
    
    # Extract quantities
    for pattern in quantity_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            try:
                value = int(match.group(1))
                results.append({
                    "value": value,
                    "type": "quantity",
                    "original": match.group(),
                    "position": match.start()
                })
            except (ValueError, IndexError):
                pass
    
    # Extract percentages
    for pattern in percent_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            try:
                value = float(match.group(1))
                results.append({
                    "value": value,
                    "type": "percentage",
                    "original": match.group(),
                    "position": match.start()
                })
            except ValueError:
                pass
    
    # Extract dates
    for pattern in date_patterns:
        for match in re.finditer(pattern, text):
            results.append({
                "value": match.group(),
                "type": "date",
                "original": match.group(),
                "position": match.start()
            })
    
    return results


def validate_response(response_text: str, context_data: Dict) -> Dict:
    """Validate LLM response against real ERPNext data.
    
    Args:
        response_text: The LLM-generated response to validate
        context_data: Dict containing real ERPNext data to validate against
            {
                "document_type": "Sales Order",
                "document_name": "SO-00754-Calipso",
                "amount": 69189.12,
                "customer": "Calipso s.r.l",
                "status": "Completed",
                "delivery_status": "Fully Delivered",
                "billing_status": "Fully Billed",
                "delivery_date": "2024-01-29",
                # ... any other real data fields
            }
    
    Returns:
        {
            "validated": bool,           # True if response matches context
            "confidence": float,         # 0.0-1.0 confidence score
            "corrections": [             # List of corrections needed
                {
                    "type": "amount_mismatch",
                    "original": "$50,000",
                    "correct": "$69,189.12",
                    "explanation": "Response claimed $50,000 but actual is $69,189.12"
                }
            ],
            "issues": [],               # List of issue descriptions
            "validated_values": {}      # Values that were checked and match
        }
    """
    corrections = []
    issues = []
    validated_values = {}
    confidence = 1.0
    
    if not response_text:
        return {
            "validated": False,
            "confidence": 0.0,
            "corrections": [],
            "issues": ["Empty response"],
            "validated_values": {}
        }
    
    # 1. Check for placeholder text (hallucination indicator)
    placeholders = re.findall(r'\[([^\]]+)\]', response_text)
    if placeholders:
        confidence -= 0.3
        issues.append(f"Contains placeholder text: {', '.join(placeholders)}")
    
    # 2. Extract numeric values from response
    response_values = extract_numeric_values(response_text)
    
    # 3. Validate against context data
    for key, expected_value in context_data.items():
        if expected_value is None:
            continue
            
        expected_value_str = str(expected_value).lower().strip()
        
        # Check for exact string matches in response
        if expected_value_str in response_text.lower():
            validated_values[key] = expected_value
        
        # Check numeric values
        if isinstance(expected_value, (int, float)) and key in ["amount", "total", "grand_total", "outstanding", "paid_amount"]:
            for rv in response_values:
                if rv["type"] == "currency":
                    # Allow 1% tolerance
                    if abs(rv["value"] - float(expected_value)) / max(float(expected_value), 1) > 0.01:
                        corrections.append({
                            "type": "amount_mismatch",
                            "original": rv["original"],
                            "correct": f"${expected_value:,.2f}",
                            "explanation": f"Response claimed {rv['original']} but actual is ${expected_value:,.2f}"
                        })
                        confidence -= 0.2
                    else:
                        validated_values[key] = expected_value
    
    # 4. Check status fields
    status_fields = ["status", "delivery_status", "billing_status", "workflow_state"]
    for field in status_fields:
        if field in context_data and context_data[field]:
            expected = str(context_data[field]).lower()
            if expected not in response_text.lower():
                # Status not mentioned in response - not necessarily wrong, just not confirmed
                pass
            else:
                validated_values[field] = context_data[field]
    
    # 5. Check document name
    if "document_name" in context_data:
        doc_name = str(context_data["document_name"])
        if doc_name in response_text:
            validated_values["document_name"] = doc_name
    
    # 6. Check customer name
    if "customer" in context_data:
        customer = str(context_data["customer"]).lower()
        # Check if customer name appears in response (partial match OK)
        customer_parts = customer.split()
        for part in customer_parts:
            if len(part) > 3 and part not in ["s.r.l", "s.a.", "s.a.b.", "inc.", "ltd."]:
                if part in response_text.lower():
                    validated_values["customer"] = context_data["customer"]
                    break
    
    # Final confidence calculation
    if corrections:
        confidence = max(0.0, confidence)
    elif issues:
        confidence = max(0.3, confidence)
    
    validated = confidence >= 0.6 and len(corrections) == 0
    
    return {
        "validated": validated,
        "confidence": confidence,
        "corrections": corrections,
        "issues": issues,
        "validated_values": validated_values
    }


def sanitize_response(response_text: str) -> Dict:
    """Remove hallucinated/placeholder data from response.
    
    Args:
        response_text: The potentially problematic response
    
    Returns:
        {
            "cleaned": str,           # The sanitized response
            "removed": [],            # List of removed items
            "safe": bool              # True if response is now safe
        }
    """
    removed = []
    cleaned = response_text
    
    # 1. Remove placeholder patterns like [Customer Name], [Amount], etc.
    placeholders = re.findall(r'\[([^\]]+)\]', cleaned)
    for placeholder in placeholders:
        removed.append(f"[{placeholder}]")
        cleaned = cleaned.replace(f"[{placeholder}]", "[DATA UNAVAILABLE]")
    
    # 2. Remove common hallucination patterns
    hallucination_patterns = [
        (r'\[\d{4}-\d{2}-\d{2}\]', 'date placeholder'),  # [YYYY-MM-DD]
        (r'\[\$[^\]]+\]', 'amount placeholder'),          # [$X,XXX]
        (r'\[.*?Name\]', 'name placeholder'),              # [X Name]
        (r'\[TODO\]', 'TODO'),
        (r'\[FIXME\]', 'FIXME'),
        (r'\[placeholder\]', 'placeholder'),
        (r'\[insert.*?\]', 'insert placeholder'),
    ]
    
    for pattern, label in hallucination_patterns:
        matches = re.findall(pattern, cleaned, re.IGNORECASE)
        for match in matches:
            removed.append(f"{label}: {match}")
            cleaned = re.sub(re.escape(match), '[DATA UNAVAILABLE]', cleaned, flags=re.IGNORECASE)
    
    # 3. Remove specific hallucination patterns
    hallucinated_fields = [
        r'(?:customer|client)[:\s]+\[.*?\]',
        r'(?:amount|total|sum)[:\s]+\[.*?\]',
        r'(?:date|due date|delivery date)[:\s]+\[.*?\]',
        r'(?:status|state)[:\s]+\[.*?\]',
    ]
    
    for pattern in hallucinated_fields:
        matches = re.findall(pattern, cleaned, re.IGNORECASE)
        for match in matches:
            removed.append(f"hallucinated field: {match}")
            cleaned = re.sub(re.escape(match), '[DATA UNAVAILABLE]', cleaned, flags=re.IGNORECASE)
    
    # 4. Check if response is now safe (has actual content)
    safe = len(removed) == 0 or len(cleaned.strip()) > 50
    
    # 5. If completely empty or just placeholders, return error message
    if not cleaned.strip() or cleaned.strip() == "[DATA UNAVAILABLE]":
        return {
            "cleaned": "❌ I don't have enough data to answer that question accurately. Please provide more context or check the document directly.",
            "removed": removed,
            "safe": False
        }
    
    return {
        "cleaned": cleaned,
        "removed": removed,
        "safe": safe
    }


def validate_and_sanitize(response_text: str, context_data: Dict = None) -> Dict:
    """Combined validation and sanitization.
    
    This is the main entry point for Phase 8A.
    
    Args:
        response_text: The LLM-generated response
        context_data: Real ERPNext data (optional but recommended)
    
    Returns:
        {
            "original": str,           # Original response
            "sanitized": str,          # After removing placeholders
            "validated": bool,         # Whether validation passed
            "confidence": float,       # 0.0-1.0
            "corrections": [],         # Required corrections
            "safe": bool,              # Whether to send to user
            "final_response": str      # The response to send to user
        }
    """
    result = {
        "original": response_text,
        "sanitized": response_text,
        "validated": True,
        "confidence": 1.0,
        "corrections": [],
        "safe": True,
        "final_response": response_text
    }
    
    # Step 1: Sanitize first (remove obvious hallucinations)
    if context_data is None:
        context_data = {}
    
    sanitize_result = sanitize_response(response_text)
    result["sanitized"] = sanitize_result["cleaned"]
    result["safe"] = sanitize_result["safe"]
    
    if sanitize_result["removed"]:
        result["corrections"].extend([f"Removed: {r}" for r in sanitize_result["removed"]])
    
    # Step 2: Validate against real data if available
    if context_data and response_text:
        validation_result = validate_response(response_text, context_data)
        result["validated"] = validation_result["validated"]
        result["confidence"] = validation_result["confidence"]
        result["corrections"].extend(validation_result["corrections"])
        
        # If validation failed but sanitized is safe, use sanitized version
        if not validation_result["validated"] and sanitize_result["safe"]:
            result["final_response"] = sanitize_result["cleaned"]
            result["safe"] = True
            result["validated"] = True
            result["confidence"] = 0.7
    
    # Step 3: Determine final response
    if not result["safe"]:
        result["final_response"] = (
            "⚠️ I cannot provide accurate information for this query. "
            "The data may be incomplete or contain errors. "
            "Please check the document directly in ERPNext."
        )
    elif result["confidence"] < 0.6:
        # Low confidence - add disclaimer
        result["final_response"] = (
            f"{result['sanitized']}\n\n"
            f"---\n*⚠️ This response was validated with {result['confidence']:.0%} confidence. "
            f"Please verify critical information directly in ERPNext.*"
        )
    
    return result
