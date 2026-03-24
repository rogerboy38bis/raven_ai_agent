# -*- coding: utf-8 -*-
"""
Phase 10.4: Document Reports API
Provides reports for documents without required files
"""

import frappe
from frappe import _
from frappe.utils import today


@frappe.whitelist()
def get_missing_documents_report(doctype: str = None):
    """
    Get report of documents missing required files.
    
    Args:
        doctype: Optional filter by doctype (Sales Order, Sales Invoice)
    
    Returns:
        List of documents missing files
    """
    if not doctype:
        doctype = frappe.form_dict.get("doctype")
    
    results = []
    
    # Sales Order - Customer PO
    if not doctype or doctype == "Sales Order":
        missing_so = frappe.db.sql("""
            SELECT 
                so.name,
                so.customer,
                so.transaction_date,
                so.customer_po_file
            FROM `tabSales Order` so
            WHERE so.customer_po_file IS NULL 
            AND so.docstatus = 1
            AND so.status NOT IN ('Closed', 'Cancelled')
            ORDER BY so.transaction_date DESC
            LIMIT 100
        """, as_dict=True)
        
        for row in missing_so:
            results.append({
                "doctype": "Sales Order",
                "docname": row.name,
                "customer": row.customer,
                "date": row.transaction_date,
                "missing_file": "Customer PO"
            })
    
    # Sales Invoice - Pedimento
    if not doctype or doctype == "Sales Invoice":
        missing_si = frappe.db.sql("""
            SELECT 
                si.name,
                si.customer,
                si.posting_date,
                si.pedimento_file
            FROM `tabSales Invoice` si
            WHERE si.pedimento_file IS NULL 
            AND si.docstatus = 1
            AND si.status NOT IN ('Closed', 'Cancelled')
            ORDER BY si.posting_date DESC
            LIMIT 100
        """, as_dict=True)
        
        for row in missing_si:
            results.append({
                "doctype": "Sales Invoice",
                "docname": row.name,
                "customer": row.customer,
                "date": row.posting_date,
                "missing_file": "Pedimento"
            })
    
    return {
        "date": today(),
        "total": len(results),
        "data": results
    }


@frappe.whitelist()
def get_document_summary():
    """
    Get summary of document file status.
    """
    summary = {}
    
    # Sales Order summary
    so_with_po = frappe.db.count("Sales Order", {
        "customer_po_file": ["is", "set"],
        "docstatus": 1
    })
    so_total = frappe.db.count("Sales Order", {
        "docstatus": 1,
        "status": ["not in", ["Closed", "Cancelled"]]
    })
    
    summary["sales_order"] = {
        "total": so_total,
        "with_customer_po": so_with_po,
        "without_customer_po": so_total - so_with_po,
        "percentage": round((so_with_po / so_total * 100) if so_total > 0 else 0, 1)
    }
    
    # Sales Invoice summary
    si_with_pedimento = frappe.db.count("Sales Invoice", {
        "pedimento_file": ["is", "set"],
        "docstatus": 1
    })
    si_total = frappe.db.count("Sales Invoice", {
        "docstatus": 1,
        "status": ["not in", ["Closed", "Cancelled"]]
    })
    
    summary["sales_invoice"] = {
        "total": si_total,
        "with_pedimento": si_with_pedimento,
        "without_pedimento": si_total - si_with_pedimento,
        "percentage": round((si_with_pedimento / si_total * 100) if si_total > 0 else 0, 1)
    }
    
    return summary
