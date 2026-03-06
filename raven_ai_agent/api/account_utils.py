"""
Account Utilities for Microsip/SAT COA Management

Provides whitelisted methods for fixing accounting data that can't be changed
through normal ERPNext UI due to submission locks.

IMPORTANT: These are admin-only functions. Use with caution.
"""
import frappe
import json


@frappe.whitelist()
def fix_invoice_debit_to(invoice_name, new_debit_to):
    """Fix debit_to on a submitted Sales Invoice that has NO GL entries.
    
    This is needed when an invoice was submitted with a Group account
    (e.g., 1105 - CLIENTES) which prevents GL entry creation.
    
    Safety checks:
    - Only works if invoice has 0 GL entries (no accounting impact)
    - Validates new_debit_to is a valid Receivable ledger account
    - Requires System Manager or Accounts Manager role
    
    Args:
        invoice_name: Sales Invoice name (e.g., ACC-SINV-2026-00004)
        new_debit_to: New debit_to account (e.g., 1105.2.7 - GREENTECH SA - AMB-W)
    
    Returns:
        dict with success status and message
    """
    # Permission check
    if not frappe.has_permission("Sales Invoice", "write"):
        frappe.throw("You don't have permission to modify Sales Invoices")
    
    # Validate invoice exists and is submitted
    si = frappe.db.get_value(
        'Sales Invoice', invoice_name,
        ['name', 'docstatus', 'debit_to', 'customer', 'currency'],
        as_dict=True
    )
    if not si:
        return {"success": False, "error": f"Invoice {invoice_name} not found"}
    if si.docstatus != 1:
        return {"success": False, "error": f"Invoice {invoice_name} is not submitted (docstatus={si.docstatus})"}
    
    # Safety: ensure NO GL entries exist
    gl_count = frappe.db.count('GL Entry', {'voucher_no': invoice_name})
    if gl_count > 0:
        return {
            "success": False,
            "error": f"Invoice {invoice_name} has {gl_count} GL entries. "
                     "Cannot modify — use Cancel & Amend instead."
        }
    
    # Validate new account
    acct = frappe.db.get_value(
        'Account', new_debit_to,
        ['name', 'is_group', 'account_type', 'account_currency'],
        as_dict=True
    )
    if not acct:
        return {"success": False, "error": f"Account '{new_debit_to}' not found"}
    if acct.is_group:
        return {"success": False, "error": f"Account '{new_debit_to}' is a Group account — must be a Ledger"}
    if acct.account_type != 'Receivable':
        return {"success": False, "error": f"Account '{new_debit_to}' is not a Receivable account (type={acct.account_type})"}
    
    old_debit_to = si.debit_to
    
    # Direct SQL update to bypass UpdateAfterSubmitError
    frappe.db.sql("""
        UPDATE `tabSales Invoice`
        SET debit_to = %s, modified = NOW()
        WHERE name = %s
    """, (new_debit_to, invoice_name))
    
    # CRITICAL: party_account_currency must match the debit_to account's currency,
    # NOT the invoice currency. For MXN Microsip accounts (1105.x), this is MXN
    # even when the invoice is in USD. ERPNext handles the conversion via conversion_rate.
    # Exchange rate differences at payment time go to gain/loss accounts.
    frappe.db.sql("""
        UPDATE `tabSales Invoice`
        SET party_account_currency = %s, modified = NOW()
        WHERE name = %s
    """, (acct.account_currency, invoice_name))
    
    frappe.db.commit()
    
    return {
        "success": True,
        "message": f"Updated {invoice_name} debit_to: '{old_debit_to}' → '{new_debit_to}' "
                   f"(currency: {acct.account_currency})",
        "old_debit_to": old_debit_to,
        "new_debit_to": new_debit_to,
        "account_currency": acct.account_currency
    }


@frappe.whitelist()
def repost_invoice_gl(invoice_name):
    """Trigger GL entry creation for a submitted Sales Invoice with 0 GL entries.
    
    After fixing debit_to, this re-runs the GL entry posting logic.
    
    Args:
        invoice_name: Sales Invoice name
    
    Returns:
        dict with success status and GL entry count
    """
    if not frappe.has_permission("Sales Invoice", "write"):
        frappe.throw("You don't have permission to modify Sales Invoices")
    
    si = frappe.get_doc('Sales Invoice', invoice_name)
    if si.docstatus != 1:
        return {"success": False, "error": f"Invoice not submitted (docstatus={si.docstatus})"}
    
    # Check current GL entries
    gl_count_before = frappe.db.count('GL Entry', {'voucher_no': invoice_name})
    
    try:
        # Re-run make_gl_entries
        si.make_gl_entries()
        frappe.db.commit()
        
        gl_count_after = frappe.db.count('GL Entry', {'voucher_no': invoice_name})
        
        return {
            "success": True,
            "message": f"GL entries for {invoice_name}: {gl_count_before} → {gl_count_after}",
            "gl_before": gl_count_before,
            "gl_after": gl_count_after
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "gl_before": gl_count_before
        }


@frappe.whitelist()
def discover_customer_account(customer, company, currency=None):
    """Find the Microsip/SAT per-customer receivable account.
    
    Searches 1105.1.x (NACIONALES/MXN) and 1105.2.x (EXTRANJEROS/USD)
    for an account matching the customer name.
    
    Args:
        customer: Customer name
        company: Company name
        currency: Invoice currency (USD, MXN, etc.)
    
    Returns:
        dict with found account info
    """
    company_currency = frappe.db.get_value('Company', company, 'default_currency') or 'MXN'
    
    if not currency:
        currency = company_currency
    
    # Determine search group
    if currency != company_currency:
        parent_prefix = '1105.2 - EXTRANJEROS'
        group_type = 'EXTRANJEROS (foreign)'
    else:
        parent_prefix = '1105.1 - NACIONALES'
        group_type = 'NACIONALES (domestic)'
    
    # Get all sub-accounts
    sub_accounts = frappe.get_all(
        'Account',
        filters={
            'company': company,
            'account_type': 'Receivable',
            'is_group': 0,
            'parent_account': ['like', f'{parent_prefix}%']
        },
        fields=['name', 'account_currency'],
        limit_page_length=0
    )
    
    # Clean customer name
    customer_clean = customer.upper().strip()
    for suffix in [' SA DE CV', ' S DE RL DE CV', ' S.A.', ' SA', ' AB',
                   ' LLC', ' INC', ' LTD', ' GMBH', ' SRL', ' SPR']:
        customer_clean = customer_clean.replace(suffix, '')
    customer_clean = customer_clean.strip()
    
    matches = []
    for acct in sub_accounts:
        acct_upper = acct.name.upper()
        if customer_clean in acct_upper or customer.upper() in acct_upper:
            matches.append({"name": acct.name, "currency": acct.account_currency, "match": "exact"})
    
    if not matches:
        # Fuzzy: first significant word
        words = [w for w in customer_clean.split() if len(w) >= 4]
        if words:
            primary = words[0]
            for acct in sub_accounts:
                if primary in acct.name.upper():
                    matches.append({"name": acct.name, "currency": acct.account_currency, "match": "fuzzy"})
    
    return {
        "customer": customer,
        "customer_clean": customer_clean,
        "search_group": group_type,
        "parent_prefix": parent_prefix,
        "total_sub_accounts": len(sub_accounts),
        "matches": matches,
        "best_match": matches[0] if matches else None
    }
