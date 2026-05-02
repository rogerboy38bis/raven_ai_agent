"""
V13.6.0 P3 Migration: Raven Webhook Handlers
Original Server Scripts: /api/method/raven_webhook_handler.handle, Raven Webhook Handler Script
Type: Whitelisted APIs
"""

import frappe

# ============================================================
# Handler 1: /api/method/raven_webhook_handler.handle
# ============================================================

from frappe import whitelist
import frappe

@frappe.whitelist(allow_guest=True)
def handle_webhook(**kwargs):
    try:
        data = frappe.request.get_json()
        
        # Validate the request if needed
        # Process the webhook data
        
        return {"success": True, "message": "Webhook processed"}
    except Exception as e:
        frappe.log_error(title="Raven Webhook Error")
        return {"success": False, "error": str(e)}

# ============================================================
# Handler 2: Raven Webhook Handler Script
# ============================================================

@frappe.whitelist(allow_guest=True)
def handle():
    # Verify secret if needed
    secret = frappe.get_request_header("X-Raven-Secret")
    if secret != frappe.conf.raven_webhook_secret:
        frappe.throw("Invalid secret", frappe.AuthenticationError)
    
    data = frappe.request.get_json()
    # Process your webhook data here
    
    return {"status": "success"}
def validate(doc, method):
    # Auto-set the webhook handler link in child table
    for row in doc.get("trigger_events", []):
        if not row.webhook_handler:
            row.webhook_handler = doc.name
    
    # Validate at least one trigger is enabled
    if not any(row.enabled for row in doc.get("trigger_events", [])):
        frappe.throw("Please enable at least one trigger event", title="Configuration Error")
        # In your hooks.py or custom app
from frappe import whitelist

@whitelist(allow_guest=True)
def handle_sales_order_webhook():
    # 1. Verify request
    verify_webhook()
    
    # 2. Get payload
    payload = frappe.request.get_json()
    so_name = payload.get('name')
    
    # 3. Process based on workflow state
    if payload.get('workflow_state') == 'Submitted':
        create_installation_project(payload)
        reserve_inventory(so_name)
        notify_team(payload)
    
    return {"success": True}

@whitelist(allow_guest=True)
def create_installation_project(payload):
    """Create project in Project Management tool"""
    project = frappe.get_doc({
        'doctype': 'Project',
        'project_name': f"Installation - {payload['customer']}",
        'expected_start_date': payload['delivery_date'],
        'sales_order': payload['name']
    }).insert()
    
# In hooks.py
def handle_sales_order(doc, method):
    if doc.doctype == 'Sales Order' and doc.workflow_state == 'Submitted':
        frappe.enqueue(
            'your_app.webhooks.process_sales_order',
            sales_order=doc.name
        )

def process_sales_order(sales_order):
    doc = frappe.get_doc('Sales Order', sales_order)
    
    payload = {
        'event': 'order_submitted',
        'order_id': doc.name,
        'customer': doc.customer_name,
        'amount': doc.grand_total
    }
    
    # Send to Raven or external system
    frappe.make_post_request(
        url='https://your-endpoint.com/webhook',
        data=payload,
        headers={'Authorization': 'Bearer your-token'}
    )

