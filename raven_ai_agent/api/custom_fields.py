"""
Custom Fields - Auto-create fields on app install
Best for Frappe Cloud deployment (no bench access needed)
"""
import frappe


def create_po_extraction_fields():
    """
    Create custom fields for Sales Order PO extraction
    
    Run this on app install or manually
    """
    
    fields = [
        {
            "dt": "Sales Order",
            "fieldname": "po_extraction_data",
            "fieldtype": "Small Text",
            "label": "PO Extraction Data",
            "description": "JSON data extracted from PO PDF",
            "insert_after": "customer",
            "hidden": 1,
            "module": "Raven AI Agent"
        },
        {
            "dt": "Sales Order",
            "fieldname": "po_extracted",
            "fieldtype": "Check",
            "label": "PO Extracted",
            "description": "Check if PO data has been extracted from attached PDF",
            "insert_after": "po_extraction_data",
            "module": "Raven AI Agent"
        },
        {
            "dt": "Sales Order",
            "fieldname": "po_extraction_status",
            "fieldtype": "Select",
            "label": "PO Extraction Status",
            "options": "Pending\nSuccess\nFailed",
            "default": "Pending",
            "insert_after": "po_extracted",
            "module": "Raven AI Agent"
        },
        {
            "dt": "Sales Order",
            "fieldname": "po_extraction_error",
            "fieldtype": "Small Text",
            "label": "PO Extraction Error",
            "hidden": 1,
            "insert_after": "po_extraction_status",
            "module": "Raven AI Agent"
        }
    ]
    
    for field in fields:
        # Check if field already exists
        if not frappe.db.exists("Custom Field", f"{field['dt']}-{field['fieldname']}"):
            doc = frappe.get_doc({
                "doctype": "Custom Field",
                "dt": field["dt"],
                "dtype": field["fieldtype"],
                "fieldname": field["fieldname"],
                "label": field["label"],
                "description": field.get("description"),
                "insert_after": field.get("insert_after"),
                "hidden": field.get("hidden", 0),
                "options": field.get("options"),
                "default": field.get("default"),
                "module": field.get("module"),
                "is_system_generated": 0
            })
            doc.insert(ignore_permissions=True)
            print(f"Created: {field['fieldname']}")
    
    frappe.db.commit()
    print("Custom fields created successfully!")


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
        cf_name = f"Sales Order-{field}"
        if frappe.db.exists("Custom Field", cf_name):
            frappe.delete_doc("Custom Field", cf_name)
            print(f"Deleted: {field}")
    
    frappe.db.commit()
    print("Custom fields removed!")
