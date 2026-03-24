# -*- coding: utf-8 -*-
"""
Phase 10.3 & 10.4: Shared Drive File Helper
Centralized helper for attaching files to DocTypes via Drive Mapping Rules
Used by UI buttons (10.2.x), bulk importer (10.3), and future automation
"""

import frappe
import os
import csv
import json
from frappe import _
from frappe.utils import now_datetime, get_datetime
from typing import Optional, Dict, List


# Map of doctypes to their link field names for Drive files
DOCTYPE_LINK_FIELD_MAP = {
    "Sales Order": "customer_po_file",
    "Sales Invoice": "pedimento_file",
}


def attach_file_via_mapping(
    doctype: str,
    docname: str,
    file_role: str,
    local_path: str = None,
    file_url: str = None,
    file_content: bytes = None,
    is_private: bool = True,
    skip_existing: bool = True
) -> dict:
    """
    Shared helper to attach a file to a DocType using Drive Mapping Rules.
    
    Args:
        doctype: Target DocType (e.g., "Sales Order", "Sales Invoice")
        docname: Name of the target document
        file_role: Role of file (e.g., "Customer PO", "Pedimento", "Supplier Invoice")
        local_path: Local filesystem path to the file
        file_url: URL of an existing file in Frappe
        file_content: Raw file content as bytes
        is_private: Whether the file should be private in Drive
        skip_existing: If True, skip if a file already exists for this doc+role
    
    Returns:
        dict with success status, drive_file, folder_path, filename, message
    """
    # Validate target document exists
    if not frappe.db.exists(doctype, docname):
        frappe.throw(_("Document {0} {1} not found").format(doctype, docname))
    
    doc = frappe.get_doc(doctype, docname)
    
    # Get mapping rule
    mapping = get_mapping_for_doctype(doctype, file_role)
    if not mapping:
        frappe.throw(_("No active Drive Mapping Rule found for {0} - {1}").format(doctype, file_role))
    
    # Get link field for this doctype
    link_field = get_link_field_for_doctype(doctype, file_role)
    
    # Check if file already exists (idempotent)
    if skip_existing and link_field:
        existing_value = doc.get(link_field)
        if existing_value:
            return {
                "success": False,
                "skipped": True,
                "message": _("File already exists for {0} - {1}").format(doctype, docname),
                "existing_file": existing_value
            }
    
    # Resolve folder and filename
    folder_path = resolve_folder_path(mapping, doc)
    filename = resolve_filename(mapping, doc, get_file_extension(local_path, file_url, file_content))
    
    # Get or create folder in Drive
    folder = ensure_drive_folder(folder_path)
    
    # Upload file to Drive
    drive_file = upload_to_drive(
        local_path=local_path,
        file_url=file_url,
        file_content=file_content,
        filename=filename,
        parent_folder=folder,
        is_private=is_private
    )
    
    # Update the link field on the target document
    if link_field:
        doc.set(link_field, drive_file.name)
        doc.save(ignore_permissions=True)
        frappe.db.commit()
    
    return {
        "success": True,
        "drive_file": drive_file.name,
        "folder_path": folder_path,
        "filename": filename,
        "link_field": link_field,
        "message": _("File uploaded successfully to {0}").format(folder_path)
    }


def get_mapping_for_doctype(doctype: str, file_role: str = None) -> dict:
    """
    Get active Drive Mapping Rule for a doctype and optional role.
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
    Replaces {name} with document name.
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
    Returns Drive Entity document.
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


def upload_to_drive(
    local_path: str = None,
    file_url: str = None,
    file_content: bytes = None,
    filename: str = None,
    parent_folder: frappe.doc = None,
    is_private: bool = True
) -> frappe.doc:
    """
    Upload file to Drive.
    """
    from frappe.utils.file_manager import get_file_url
    
    # Get team
    team = frappe.db.get_value("Drive Settings", None, "default_team") or "Default"
    
    file_doc = None
    
    # Handle file upload
    if local_path:
        # Upload from local filesystem
        if not os.path.exists(local_path):
            frappe.throw(_("File not found: {0}").format(local_path))
        
        with open(local_path, "rb") as f:
            file_content = f.read()
        
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": filename or os.path.basename(local_path),
            "content": file_content,
            "is_private": 1 if is_private else 0
        })
        file_doc.insert()
        
    elif file_url:
        # Upload from existing URL
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_url": file_url,
            "file_name": filename,
            "is_private": 1 if is_private else 0
        })
        file_doc.insert()
        
    elif file_content:
        # Upload from bytes
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": filename,
            "content": file_content,
            "is_private": 1 if is_private else 0
        })
        file_doc.insert()
    else:
        frappe.throw(_("No file provided (local_path, file_url, or file_content required)"))
    
    # Create Drive File from this File
    drive_file = create_drive_file_from_file(file_doc, parent_folder, team)
    
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


def get_link_field_for_doctype(doctype: str, file_role: str = None) -> str:
    """
    Get the link field name for a doctype and file role.
    """
    # Try exact match first
    if doctype in DOCTYPE_LINK_FIELD_MAP:
        return DOCTYPE_LINK_FIELD_MAP[doctype]
    
    # Fallback: try to find via Custom Field
    custom_field = frappe.db.get_value(
        "Custom Field",
        {"dt": doctype, "fieldtype": "Link", "options": ["in", ["File", "Drive File"]]},
        "fieldname"
    )
    
    return custom_field


def get_file_extension(local_path: str = None, file_url: str = None, file_content: bytes = None) -> str:
    """
    Determine file extension from various sources.
    """
    if local_path:
        ext = os.path.splitext(local_path)[1]
        if ext:
            return ext.lstrip(".")
    
    if file_url:
        ext = os.path.splitext(file_url)[1]
        if ext:
            return ext.lstrip(".")
    
    # Default to pdf
    return "pdf"


# ============================================================================
# PHASE 10.3: BULK IMPORT FUNCTIONS
# ============================================================================

def bulk_import_from_csv(
    csv_path: str,
    dry_run: bool = False,
    skip_existing: bool = True,
    batch_size: int = 50
) -> dict:
    """
    Bulk import files from a CSV mapping file.
    
    CSV Format:
        file_path,target_doctype,docname,file_role
    
    Args:
        csv_path: Path to the CSV file
        dry_run: If True, only validate without uploading
        skip_existing: Skip if file already exists for doc+role
        batch_size: Number of files to process per batch
    
    Returns:
        dict with results summary
    """
    results = {
        "total": 0,
        "success": 0,
        "skipped": 0,
        "failed": 0,
        "errors": [],
        "dry_run": dry_run
    }
    
    if not os.path.exists(csv_path):
        frappe.throw(_("CSV file not found: {0}").format(csv_path))
    
    # Read CSV
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    results["total"] = len(rows)
    
    # Process in batches
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        
        for row in batch:
            try:
                file_path = row.get("file_path", "").strip()
                target_doctype = row.get("target_doctype", "").strip()
                docname = row.get("docname", "").strip()
                file_role = row.get("file_role", "").strip()
                
                if not all([file_path, target_doctype, docname, file_role]):
                    results["failed"] += 1
                    results["errors"].append({
                        "file": file_path,
                        "error": "Missing required fields"
                    })
                    continue
                
                # Validate mapping exists
                mapping = get_mapping_for_doctype(target_doctype, file_role)
                if not mapping:
                    results["failed"] += 1
                    results["errors"].append({
                        "file": file_path,
                        "error": f"No Drive Mapping Rule for {target_doctype} - {file_role}"
                    })
                    continue
                
                if dry_run:
                    # Just validate
                    results["skipped"] += 1
                else:
                    # Actually upload
                    result = attach_file_via_mapping(
                        doctype=target_doctype,
                        docname=docname,
                        file_role=file_role,
                        local_path=file_path,
                        skip_existing=skip_existing
                    )
                    
                    if result.get("success"):
                        results["success"] += 1
                    elif result.get("skipped"):
                        results["skipped"] += 1
                    else:
                        results["failed"] += 1
                        results["errors"].append({
                            "file": file_path,
                            "error": result.get("message", "Unknown error")
                        })
                        
            except Exception as e:
                results["failed"] += 1
                results["errors"].append({
                    "file": row.get("file_path", "unknown"),
                    "error": str(e)
                })
    
    return results


def bulk_import_from_directory(
    directory: str,
    target_doctype: str,
    file_role: str,
    filename_pattern: str = None,
    dry_run: bool = False,
    skip_existing: bool = True
) -> dict:
    """
    Bulk import files from a directory using filename patterns.
    
    Filename pattern: SO-00045_PO.pdf -> Sales Order SO-00045, role Customer PO
    
    Args:
        directory: Path to directory containing files
        target_doctype: Target DocType for all files
        file_role: File role (e.g., "Customer PO", "Pedimento")
        filename_pattern: Optional pattern to parse docname from filename
        dry_run: If True, only validate without uploading
        skip_existing: Skip if file already exists
    
    Returns:
        dict with results summary
    """
    results = {
        "total": 0,
        "success": 0,
        "skipped": 0,
        "failed": 0,
        "errors": [],
        "dry_run": dry_run
    }
    
    if not os.path.exists(directory):
        frappe.throw(_("Directory not found: {0}").format(directory))
    
    # Get all PDF files
    files = [f for f in os.listdir(directory) if f.endswith(".pdf")]
    results["total"] = len(files)
    
    # Get mapping
    mapping = get_mapping_for_doctype(target_doctype, file_role)
    if not mapping:
        frappe.throw(_("No Drive Mapping Rule for {0} - {1}").format(target_doctype, file_role))
    
    for filename in files:
        try:
            file_path = os.path.join(directory, filename)
            
            # Parse docname from filename if pattern provided
            # Default pattern: {ROLE}_{DOCNAME}.pdf or {DOCNAME}_{ROLE}.pdf
            docname = parse_docname_from_filename(filename, file_role)
            
            if not docname:
                results["failed"] += 1
                results["errors"].append({
                    "file": filename,
                    "error": "Could not parse docname from filename"
                })
                continue
            
            if dry_run:
                results["skipped"] += 1
            else:
                result = attach_file_via_mapping(
                    doctype=target_doctype,
                    docname=docname,
                    file_role=file_role,
                    local_path=file_path,
                    skip_existing=skip_existing
                )
                
                if result.get("success"):
                    results["success"] += 1
                elif result.get("skipped"):
                    results["skipped"] += 1
                else:
                    results["failed"] += 1
                    results["errors"].append({
                        "file": filename,
                        "error": result.get("message", "Unknown error")
                    })
                    
        except Exception as e:
            results["failed"] += 1
            results["errors"].append({
                "file": filename,
                "error": str(e)
            })
    
    return results


def parse_docname_from_filename(filename: str, file_role: str) -> str:
    """
    Parse document name from filename based on common patterns.
    
    Patterns:
        - SO-00045_PO.pdf -> Sales Order SO-00045
        - PEDIMENTO_SINV-00023.pdf -> Sales Invoice SINV-00023
        - CustomerPO_SO-00045.pdf -> Sales Order SO-00045
    """
    import re
    
    # Remove extension
    name = os.path.splitext(filename)[0]
    
    # Common prefixes
    prefixes = {
        "Customer PO": ["PO", "CUSTOMER_PO", "CUSTOMERPO"],
        "Pedimento": ["PEDIMENTO", "PED", "PEDIMENTO_"],
        "Supplier Invoice": ["SUPPLIER_INVOICE", "SI", "INVOICE_"],
        "External COA": ["COA", "EXTERNAL_COA"],
    }
    
    role_prefixes = prefixes.get(file_role, [file_role])
    
    for prefix in role_prefixes:
        # Try pattern: PREFIX_DOCNAME or DOCNAME_PREFIX
        pattern = rf"^{prefix}[_-](.+)$"
        match = re.match(pattern, name, re.IGNORECASE)
        if match:
            return match.group(1)
        
        # Try reverse pattern
        pattern = rf"^(.+)[_-]{prefix}$"
        match = re.match(pattern, name, re.IGNORECASE)
        if match:
            return match.group(1)
    
    # If no pattern match, return the whole name (may work if filename = docname)
    return name


# ============================================================================
# PHASE 10.4: REPORT FUNCTIONS
# ============================================================================

def get_documents_without_file(doctype: str, file_role: str) -> List[dict]:
    """
    Get list of documents without a specific file type.
    Used for Phase 10.4 reports.
    """
    link_field = get_link_field_for_doctype(doctype, file_role)
    
    if not link_field:
        frappe.throw(_("No link field found for {0}").format(doctype))
    
    # Get all docs of this type where the link field is empty
    docs = frappe.get_all(
        doctype,
        filters={
            link_field: ["is", "not set"],
            "docstatus": ["!=", 2]  # Not cancelled
        },
        fields=["name", "customer"]
    )
    
    return docs


def get_document_file_status(doctype: str, docname: str) -> dict:
    """
    Get the status of all linked files for a document.
    """
    doc = frappe.get_doc(doctype, docname)
    
    status = {
        "doctype": doctype,
        "docname": docname,
        "files": []
    }
    
    # Check all known link fields
    for field_name in DOCTYPE_LINK_FIELD_MAP.values():
        if hasattr(doc, field_name):
            file_name = doc.get(field_name)
            if file_name:
                # Get file details
                file_exists = frappe.db.exists("Drive File", file_name)
                status["files"].append({
                    "field": field_name,
                    "file": file_name,
                    "status": "linked" if file_exists else "missing"
                })
            else:
                status["files"].append({
                    "field": field_name,
                    "file": None,
                    "status": "not_uploaded"
                })
    
    return status
