"""
PO Extractor Automation
Automatically extracts PO data when PDF is attached to Sales Order

Best Practices:
- Use doc_events hook on File
- Process in background with frappe.enqueue
- Store results in custom fields
"""
import frappe
import json
from datetime import datetime


def setup_hooks():
    """
    Configure hooks for PO extraction
    
    Add to hooks.py:
    ----
    doc_events = {
        "File": {
            "after_insert": "raven_ai_agent.api.po_extractor.on_file_added"
        }
    }
    """
    pass


def on_file_added(doc, method):
    """
    Triggered when a new file is added
    Checks if it's a PDF attached to a Sales Order
    """
    # Check if file is PDF
    if not doc.file_url:
        return
    
    file_ext = doc.file_url.lower().split('.')[-1] if '.' in doc.file_url else ''
    if file_ext != 'pdf':
        return
    
    # Check if attached to Sales Order
    if doc.attached_to_doctype == 'Sales Order':
        frappe.enqueue(
            "raven_ai_agent.api.po_extractor.extract_po_from_attachment",
            file_docname=doc.name,
            sales_order_name=doc.attached_to_name,
            timeout=300,
            queue="long"
        )
        frappe.msgprint("PO extraction started in background")


@frappe.whitelist()
def extract_po_from_attachment(file_docname, sales_order_name):
    """
    Extract PO data from attachment (background job)
    """
    try:
        # Get file
        file_doc = frappe.get_doc("File", file_docname)
        
        # Get Sales Order
        so = frappe.get_doc("Sales Order", sales_order_name)
        
        # Extract using MultimodalIngest
        from raven_ai_agent.api.multimodal_ingest import MultimodalIngest
        
        ingest = MultimodalIngest(user=so.owner)
        
        result = ingest.ingest_file(
            file_doc.file_url,
            "application/pdf",
            "Extract: PO number, customer, items with quantities and prices, total, delivery address"
        )
        
        # Store results in Sales Order custom fields
        if "error" not in result:
            # Create/update extraction data
            extraction_data = {
                "po_number": result.get("po_number"),
                "customer": result.get("customer"),
                "date": result.get("date"),
                "items": result.get("items", []),
                "total": result.get("total"),
                "address": result.get("address"),
                "extracted_at": frappe.utils.now(),
                "file_name": file_doc.file_name
            }
            
            # Save to custom field (if exists) or create a child table entry
            try:
                so.po_extraction_data = json.dumps(extraction_data)
                so.po_extracted = 1
                so.po_extraction_status = "Success"
                so.save(ignore_permissions=True)
                frappe.db.commit()
            except Exception as e:
                frappe.logger().error(f"Failed to save extraction: {e}")
            
            # Notify via Raven
            notify_user(so, extraction_data, result)
            
            return {"status": "success", "data": extraction_data}
        else:
            # Handle error
            so.po_extraction_status = "Failed"
            so.po_extraction_error = result.get("error")
            so.save(ignore_permissions=True)
            frappe.db.commit()
            
            return {"status": "error", "message": result.get("error")}
            
    except Exception as e:
        frappe.logger().error(f"PO Extraction failed: {e}")
        return {"status": "error", "message": str(e)}


def notify_user(sales_order, extraction_data, raw_result):
    """
    Send notification to user via Raven or Inbox
    """
    message = f"""
📄 **PO Extraction Complete**

**Sales Order:** {sales_order.name}
**Customer:** {extraction_data.get('customer')}
**PO Number:** {extraction_data.get('po_number')}
**Date:** {extraction_data.get('date')}
**Total:** {extraction_data.get('total')}

**Items:**
{chr(10).join([f"- {item.get('product', item.get('item', 'N/A'))}: {item.get('quantity', item.get('qty', 0))} x {item.get('price_per_unit', item.get('rate', 0))}" for item in extraction_data.get('items', [])])}

**Delivery Address:** {extraction_data.get('address', 'N/A')}
    """
    
    # Try to send via Raven
    try:
        from raven_ai_agent.api.raven_client import send_message
        send_message(
            recipient=sales_order.owner,
            message=message,
            reference_doctype="Sales Order",
            reference_docname=sales_order.name
        )
    except:
        # Fallback to Inbox
        frappe.flags.ignore_permissions = True
        notification = frappe.get_doc({
            "doctype": "Notification Log",
            "subject": f"PO Extraction - {sales_order.name}",
            "content": message,
            "for_user": sales_order.owner,
            "type": "Info",
            "document_type": "Sales Order",
            "document_name": sales_order.name
        })
        notification.insert(ignore_permissions=True)
        frappe.db.commit()


@frappe.whitelist()
def validate_po_against_so(sales_order_name):
    """
    Compare extracted PO data with Sales Order items
    """
    so = frappe.get_doc("Sales Order", sales_order_name)
    
    # Get extracted data
    if not so.po_extraction_data:
        return {"error": "No extraction data found"}
    
    import json
    po_data = json.loads(so.po_extraction_data)
    
    # Compare items
    validation = {
        "po_items": po_data.get("items", []),
        "so_items": [],
        "matches": [],
        "differences": []
    }
    
    # Get SO items
    for item in so.items:
        validation["so_items"].append({
            "item_code": item.item_code,
            "item_name": item.item_name,
            "qty": item.qty,
            "rate": item.rate,
            "amount": item.amount
        })
    
    # Simple comparison
    po_total = 0
    for po_item in po_data.get("items", []):
        po_qty = float(po_item.get("quantity", po_item.get("qty", 0)))
        po_price = float(po_item.get("price_per_unit", po_item.get("rate", 0)))
        po_total += po_qty * po_price
    
    so_total = so.total
    
    validation["summary"] = {
        "po_total": po_total,
        "so_total": so_total,
        "difference": abs(po_total - so_total),
        "match": abs(po_total - so_total) < 1  # Within $1 tolerance
    }
    
    return validation


# API for manual trigger
@frappe.whitelist()
def manual_extract(sales_order_name):
    """
    Manually trigger PO extraction for a Sales Order
    """
    # Find PDF attachments
    files = frappe.get_list("File", 
        filters={
            "attached_to_doctype": "Sales Order",
            "attached_to_name": sales_order_name,
            "file_url": ["like", "%.pdf"]
        },
        fields=["name", "file_url", "file_name"]
    )
    
    if not files:
        return {"error": "No PDF found"}
    
    # Trigger extraction
    frappe.enqueue(
        "raven_ai_agent.api.po_extractor.extract_po_from_attachment",
        file_docname=files[0].name,
        sales_order_name=sales_order_name,
        timeout=300,
        queue="long"
    )
    
    return {"status": "queued", "file": files[0]}
