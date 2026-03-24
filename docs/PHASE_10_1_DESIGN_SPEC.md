# Phase 10.1 – Smart Drive & File Management: Design Specification

## Overview

Phase 10 aims to transform ERPNext into a usable DMS so users can reliably attach and find key PDFs directly from their documents (Sales Orders, Invoices, COA, Stock Entries), instead of everything being dumped into `/public/files`.

This document (Sub-Phase 10.1) defines the business-aware file structure design. After sign-off, implementation will follow in Sub-Phases 10.2–10.4.

---

## 1. Related App: rogerboy38/drive

This phase integrates with the forked Frappe Drive app: **https://github.com/rogerboy38/drive**

### About the App
- Forked from: `frappe/drive`
- Status: Beta
- Features: File manager, folder structure, user sharing, permissions
- Technology: Frappe Framework + Vue + TipTap

### Integration Approach
We will not build a full Drive from scratch. Instead:
- Use the core File DocType for storage & permissions
- Use Drive app for the UI layer
- Add a thin integration layer (Drive Mapping Rule) that understands ERPNext doctypes and business rules

---

## 1. Target DocTypes and File Roles (First Wave)

| DocType | File Role | Description | Example |
|---------|-----------|-------------|---------|
| **Sales Order** | Customer PO | Purchase order from customer | PO_0753.pdf |
| **Sales Invoice** | Pedimento | Customs import document | PEDIMENTO_2026_001.pdf |
| **COA (Quality)** | External Lab Analysis | Third-party lab test results | COA_LAB_2026_001.pdf |
| **Stock Entry** | Supplier Invoice | Invoice from supplier for materials | SUP_INV_2026_001.pdf |

### Rationale
- These 4 doctypes cover the most common "external document" attachments mentioned by stakeholders
- Each has a clear, single file role in the business workflow
- Easy to expand to other doctypes in future waves (Purchase Order, Delivery Note, etc.)

---

## 2. Folder Templates

### Base Folder Structure
```
Drive/
├── Sales Orders/
│   └── {name}/
│       └── PO_{name}.pdf
├── Sales Invoices/
│   └── {name}/
│       └── PEDIMENTO_{name}.pdf
├── Quality/
│   └── COA/
│       └── {name}/
│           └── LAB_ANALYSIS_{name}.pdf
└── Stock Entries/
    └── {name}/
        └── SUPPLIER_INVOICE_{name}.pdf
```

### Mapping Table

| DocType | Folder Template | Filename Template |
|---------|-----------------|-------------------|
| Sales Order | `Drive/Sales Orders/{name}/` | `PO_{name}.pdf` |
| Sales Invoice | `Drive/Sales Invoices/{name}/` | `PEDIMENTO_{name}.pdf` |
| COA | `Drive/Quality/COA/{name}/` | `LAB_ANALYSIS_{name}.pdf` |
| Stock Entry | `Drive/Stock Entries/{name}/` | `SUPPLIER_INVOICE_{name}.pdf` |

### Notes
- `{name}` is replaced with the actual document name (e.g., SO-00752-LEGOSAN AB)
- Spaces in names are handled by the system during file creation
- All folders are created under the private Drive root (not `/public/files`)

---

## 3. Link-to-File Fields

To display file links directly on ERPNext forms, add these fields:

| DocType | Field Name | Field Type | Label |
|---------|------------|------------|-------|
| Sales Order | `customer_po_file` | Link (File) | Customer PO |
| Sales Invoice | `pedimento_file` | Link (File) | Pedimento |
| COA | `external_analysis_file` | Link (File) | External Lab Analysis |
| Stock Entry | `supplier_invoice_file` | Link (File) | Supplier Invoice |

### UX Behavior
1. User clicks "Upload" button next to the field
2. System uses Drive Mapping Rule (Section 4) to:
   - Determine correct folder based on doctype
   - Create folder if it doesn't exist
   - Upload and store the file privately
3. Link field displays the filename; clicking opens the PDF
4. File is linked, not embedded—a single source of truth

---

## 4. Privacy Policy

**Phase 10 Policy:** All business documents (POs, invoices, pedimentos, COA PDFs) are **private by default**.

### Implementation
- Files are stored in Drive (private area), not `/public/files`
- Access is controlled via ERPNext permission system on the File doctype
- Only users with access to the parent document can view the file
- Future: Add hooks to enforce privacy on File create/update events

### Rationale
- Customer POs contain pricing and terms
- Pedimentos contain customs details
- COAs contain proprietary formulation data
- Supplier invoices contain sensitive pricing

---

## 5. Drive Mapping Rule DocType

### Purpose
Central configuration that defines for each doctype/file role:
- Where files should be stored (folder)
- How files should be named (filename pattern)

### DocType Definition

**DocType:** Drive Mapping Rule
**Module:** Raven AI Agent (or Drive App)
**Is Submittable:** No

| Field | Type | Options | Description |
|-------|------|---------|-------------|
| `doctype` | Link | DocType | Target ERPNext doctype (e.g., Sales Order) |
| `file_role` | Select | Customer PO, Supplier Invoice, Pedimento, External COA, Production Record, Other | Purpose of the file |
| `folder_template` | Data | | Folder path template (e.g., Drive/Sales Orders/{name}/) |
| `filename_template` | Data | | Filename pattern (e.g., PO_{name}.pdf) |
| `is_active` | Check | | Enable/disable this mapping |
| `description` | Text | | Notes about this mapping |

### Example Data

| doctype | file_role | folder_template | filename_template | is_active |
|---------|-----------|-----------------|-------------------|------------|
| Sales Order | Customer PO | Drive/Sales Orders/{name}/ | PO_{name}.pdf | 1 |
| Sales Invoice | Pedimento | Drive/Sales Invoices/{name}/ | PEDIMENTO_{name}.pdf | 1 |
| COA | External COA | Drive/Quality/COA/{name}/ | LAB_ANALYSIS_{name}.pdf | 1 |
| Stock Entry | Supplier Invoice | Drive/Stock Entries/{name}/ | SUPPLIER_INVOICE_{name}.pdf | 1 |

---

## 6. Integration with Raven AI Agent

### Reuse Existing Components
The document resolver from `raven_ai_agent` will be used for bulk import:
- `resolve_document_name("Sales Order", "0752")` → `SO-00752-LEGOSAN AB`
- This enables auto-attachment of legacy files based on naming conventions

### Future Integration Points
- Bulk import tool will query Drive Mapping Rules to determine where to place files
- @workflow commands may be extended to show linked files on documents
- File-linked alerts can notify users when new documents are attached

---

## 7. Deliverables Summary

| Item | Description |
|------|-------------|
| ✅ Target DocTypes | 4 doctypes defined with file roles |
| ✅ Folder Templates | Standardized path per doctype |
| ✅ Naming Templates | Consistent filename patterns |
| ✅ Link Fields | Field names for ERPNext forms |
| ✅ Privacy Policy | Private-by-default agreement |
| ✅ Drive Mapping Rule | Already exists in drive app |
| ✅ Drive API Research | Documented available methods |

---

## 8. Drive API Research

### Available Drive DocTypes

| DocType | Purpose |
|---------|---------|
| **Drive File** | Core file entity - stores file metadata, content path, permissions |
| **Drive Entity** | Base entity for files and folders |
| **Drive Document** | Wrapper for ERPNext documents in Drive |
| **Drive Team** | Team/workspace for organizing files |
| **Drive Team Member** | Team membership and roles |
| **Drive Permission** | Access control between users/teams |
| **Drive Settings** | Global Drive configuration |
| **Drive Mapping Rule** | Already exists - defines folder/filename templates |

### Key API Methods

#### File Upload (`drive.api.files.upload_file`)

```python
# Server-side call
frappe.call({
    method: "drive.api.files.upload_file",
    args: {
        team: "Drive Team Name",
        parent: "parent_folder_name",
        fullpath: "folder/subfolder/",
        transfer: 0,
        embed: 0,
    }
})
```

#### Drive Mapping Rule API (Already Implemented!)

```python
# Get mapping for a doctype
frappe.call({
    method: "drive_mapping_rule.get_mapping_for_doctype",
    args: { doctype: "Sales Order", file_role: "Customer PO" }
})
# Returns: {folder_template, filename_template, file_role}

# Resolve folder path
frappe.call({
    method: "drive_mapping_rule.resolve_folder_path",
    args: { doctype: "Sales Order", docname: "SO-00752" }
})
# Returns: "Drive/Sales Orders/SO-00752/"
```

---

## 9. Implementation Architecture

### Components

| Component | Location | Purpose |
|-----------|----------|---------|
| Drive Mapping Rule | `drive` app | Folder/filename templates (EXISTING) |
| File Upload Hook | `raven_ai_agent` | Handle upload events |
| Link Fields | ERPNext Custom Fields | Display file links on forms |
| Bulk Import | `raven_ai_agent` | Import legacy PDFs |

### Workflow

```
User uploads file → Hook triggers → Get Drive Mapping Rule → 
Resolve folder + filename → Create folder in Drive → 
Upload file → Update link field on DocType
```

---

## 10. Sign-Off

**This design specification is ready for review.**

Once approved, the next sub-phases are:

- **10.2** – Implement file hooks + upload UI + link fields
- **10.3** – Bulk import tool for legacy PDFs using naming conventions
- **10.4** – Drive UI enhancements and training materials

---

## Questions for Stakeholder Confirmation

1. ✅ Do these 4 doctypes (Sales Order, Sales Invoice, COA, Stock Entry) cover the first wave requirements?
2. ✅ Do the folder and naming templates match your file organization?
3. ✅ Is the "private by default" privacy policy correct?
4. ✅ Are the Link-to-File field names intuitive for users?
5. ✅ Should we add any additional doctypes to the first wave?
6. ✅ Is the Drive API integration approach clear?

---

*Document Author: MiniMax Agent*
*Date: 2026-03-25*
*Phase: 10.1*