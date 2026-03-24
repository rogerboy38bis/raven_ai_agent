# -*- coding: utf-8 -*-
"""
Phase 10.2.1: Upload Customer PO for Sales Order
Handles file upload to Drive and links to Sales Order
"""

import frappe
import os
from frappe import _
from frappe.utils import get_datetime, now_datetime


@frappe.whitelist()
def upload_customer_po(sales_order_name: str, file_url: str = None, file_content: str = None):
    """
    Upload Customer PO PDF for a Sales Order to Drive.
    
    Args:
        sales_order_name: Name of the Sales Order
        file_url: URL of file (if uploading from existing file)
        file_content: Base64 encoded file content (if direct upload)
    
    Returns:
        dict with success status, drive_file_name, message
    """
    # Validate Sales Order
    if not sales_order_name:
        frappe.throw(_("Sales Order name is required"))
    
    if not frappe.db.exists("Sales Order", sales_order_name):
        frappe.throw(_("Sales Order {0} not found").format(sales_order_name))
    
    sales_order = frappe.get_doc("Sales Order", sales_order_name)
    
    # Get mapping for Sales Order Customer PO
    mapping = get_mapping_for_doctype("Sales Order", "Customer PO")
    if not mapping:
        frappe.throw(_("No active Drive Mapping Rule found for Sales Order Customer PO"))
    
    # Resolve folder and filename
    folder_path = resolve_folder_path(mapping, sales_order)
    filename = resolve_filename(mapping, sales_order, "pdf")
    
    # Get or create folder in Drive
    folder = ensure_drive_folder(folder_path)
    
    # Upload file to Drive
    drive_file = upload_to_drive(
        file_url=file_url,
        file_content=file_content,
        filename=filename,
        parent_folder=folder,
        is_private=True
    )
    
    # Update Sales Order link field
    sales_order.customer_po_file = drive_file.name
    sales_order.save(ignore_permissions=True)
    
    frappe.db.commit()
    
    return {
        "success": True,
        "drive_file": drive_file.name,
        "folder_path": folder_path,
        "message": _("Customer PO uploaded successfully to {0}").format(folder_path)
    }


def get_mapping_for_doctype(doctype: str, file_role: str = None) -> dict:
    """
    Get active Drive Mapping Rule for a doctype.
    """
    filters = {
        "target_doctype": doctype,
        "is_active": 1
    }
    
    if file_role:
        filters["file_role"] = file_role
    
    mapping = frappe.get_all(
        "Drive Mapping Rule",
        filters=filters,
        fields=["name", "folder_template", "filename_template", "file_role"],
        limit=1
    )
    
    if mapping:
        return mapping[0]
    return None


def resolve_folder_path(mapping: dict, doc: frappe.doc) -> str:
    """
    Resolve folder path from template.
    
    Replaces {name} with document name
    """
    folder_template = mapping.get("folder_template", "")
    folder_path = folder_template.replace("{name}", doc.name)
    return folder_path


def resolve_filename(mapping: dict, doc: frappe.doc, extension: str = "pdf") -> str:
    """
    Resolve filename from template.
    """
    filename_template = mapping.get("filename_template", "")
    filename = filename_template.replace("{name}", doc.name)
    
    # Ensure proper extension
    if not filename.endswith(f".{extension}"):
        filename = f"{filename}.{extension}"
    
    return filename


def ensure_drive_folder(folder_path: str) -> frappe.doc:
    """
    Ensure Drive folder exists, create if needed.
    Returns Drive Entity or Drive Folder document.
    """
    from drive.api.files import get_or_create_folder
    
    # Get default team
    team = frappe.db.get_value("Drive Settings", None, "default_team") or "Default"
    
    # Try to find existing folder
    existing = frappe.db.exists("Drive Entity", {
        "name": ["like", f"%{folder_path}%"],
        "is_folder": 1
    })
    
    if existing:
        return frappe.get_doc("Drive Entity", existing)
    
    # Create folder using Drive API
    folder = get_or_create_folder(folder_path, team)
    return folder


def upload_to_drive(file_url: str = None, file_content: str = None, 
                   filename: str = None, parent_folder: str = None,
                   is_private: bool = True) -> frappe.doc:
    """
    Upload file to Drive.
    """
    from drive.api.files import upload_file
    from frappe.utils.file_manager import save_file
    
    # Get team
    team = frappe.db.get_value("Drive Settings", None, "default_team") or "Default"
    
    # Handle file upload
    if file_url:
        # Upload from existing URL
        # Use frappe file manager to create File doc first
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_url": file_url,
            "file_name": filename,
            "is_private": 1 if is_private else 0
        })
        file_doc.insert()
        
        # Now create Drive File from this File
        drive_file = create_drive_file_from_file(file_doc, parent_folder, team)
        
    elif file_content:
        # Upload from base64 content
        import base64
        import io
        
        # Decode base64 content
        file_bytes = base64.b64decode(file_content)
        
        # Create temporary file
        from tempfile import NamedTemporaryFile
        with NamedTemporaryFile(delete=False, suffix=f".{filename.split('.')[-1]}") as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        
        try:
            # Read file and create File doc
            with open(tmp_path, "rb") as f:
                file_content = f.read()
            
            file_doc = frappe.get_doc({
                "doctype": "File",
                "file_name": filename,
                "content": file_content,
                "is_private": 1 if is_private else 0
            })
            file_doc.insert()
            
            # Create Drive File
            drive_file = create_drive_file_from_file(file_doc, parent_folder, team)
            
        finally:
            # Cleanup temp file
            os.unlink(tmp_path)
    else:
        frappe.throw(_("No file provided"))
    
    return drive_file


def create_drive_file_from_file(file_doc: frappe.doc, parent_folder, team: str) -> frappe.doc:
    """
    Create Drive File from Frappe File document.
    """
    # Create Drive File document
    drive_file = frappe.get_doc({
        "doctype": "Drive File",
        "title": file_doc.file_name,
        "file": file_doc.name,
        "parent_drive_entity": parent_folder.name if parent_folder else None,
        "team": team,
        "is_private": 1
    })
    drive_file.insert()
    
    return drive_file
