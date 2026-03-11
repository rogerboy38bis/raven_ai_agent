"""
Custom Fields - Auto-create fields on app install
Best for Frappe Cloud deployment (no bench access needed)
"""
import frappe
from frappe.customize.custom_field import create_custom_fields


def create_po_extraction_fields():
    """
    Create custom fields for Sales Order PO extraction
    
    Run this on app install or manually
    """
    
    fields = {
        "Sales Order": [
            {
                "fieldname": "po_extraction_data",
                "fieldtype": "Small Text",
                "label": "PO Extraction Data",
                "description": "JSON data extracted from PO PDF",
                "insert_after": "customer",
                "hidden": 1,
                "module": "Raven AI Agent"
            },
            {
                "fieldname": "po_extracted",
                "fieldtype": "Check",
                "label": "PO Extracted",
                "description": "Check if PO data has been extracted from attached PDF",
                "insert_after": "po_extraction_data",
                "module": "Raven AI Agent"
            },
            {
                "fieldname": "po_extraction_status",
                "fieldtype": "Select",
                "label": "PO Extraction Status",
                "options": "Pending\nSuccess\nFailed",
                "default": "Pending",
                "insert_after": "po_extracted",
                "module": "Raven AI Agent"
            },
            {
                "fieldname": "po_extraction_error",
                "fieldtype": "Small Text",
                "label": "PO Extraction Error",
                "hidden": 1,
                "insert_after": "po_extraction_status",
                "module": "Raven AI Agent"
            }
        ]
    }
    
    create_custom_fields(fields)


def delete_po_extraction_fields():
    """
    Remove custom fields on app uninstall
    """
    fields_to_remove = [
        "po_extraction_data",
        "po_extracted", 
        "po_extraction_status",
        "po_extraction_error"
    ]
    
    for field in fields_to_remove:
        if frappe.db.exists("Custom Field", f"Sales Order-{field}"):
            frappe.delete_doc("Custom Field", f"Sales Order-{field}")
    
    frappe.db.commit()
