"""
V13.6.0 P3 Migration: Sales Order Webhook Handlers
Original Server Scripts: sales_order_webhook.handler, Sales Order Webhook Handler
Type: Whitelisted APIs
"""

import frappe
import hmac
import hashlib

# ============================================================
# Handler 1: sales_order_webhook.handler
# ============================================================

import frappe
import hmac
import hashlib

@frappe.whitelist(allow_guest=True)
def handler():
    # 1. Verify the webhook secret (from Raven Webhook Handler)
    webhook_config = frappe.get_doc("Raven Webhook Handler", "Sales Order Webhook")  # Replace with your Webhook Handler name
    secret = webhook_config.get_password("secret_key")  # Gets the encrypted secret
    
    # 2. Validate HMAC signature
    received_signature = frappe.get_request_header("X-Raven-Signature")
    payload = frappe.request.get_data(as_text=True)
    
    computed_signature = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(received_signature, computed_signature):
        frappe.throw("Invalid signature", frappe.AuthenticationError)
    
    # 3. Process the Sales Order data
    data = frappe.parse_json(payload)
    sales_order = data.get("doc")  # Contains the full Sales Order data
    
    if sales_order.get("docstatus") == 1:  # Submitted SO
        # Example: Create a Project from the Sales Order
        project = frappe.get_doc({
            "doctype": "Project",
            "project_name": f"Installation - {sales_order.get('name')}",
            "sales_order": sales_order.get("name"),
            "expected_start_date": sales_order.get("delivery_date")
        }).insert()
        
        frappe.db.commit()
        
        return {"success": True, "project_id": project.name}
    
    return {"success": False, "error": "Sales Order not submitted"}

# ============================================================
# Handler 2: Sales Order Webhook Handler
# ============================================================

import frappe
import hmac
import hashlib

@frappe.whitelist(allow_guest=True)
def handler():
    # 1. Verify signature
    secret = frappe.get_site_config().so_webhook_secret
    signature = frappe.get_request_header("X-Signature")
    payload = frappe.request.get_data(as_text=True)
    
    if not secret:
        frappe.throw("Webhook secret not configured")
    
    computed_sig = hmac.new(
        secret.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(signature, computed_sig):
        frappe.throw("Invalid signature", frappe.AuthenticationError)

    # 2. Process payload
    data = frappe.parse_json(payload)
    
    if data.get('event') == 'sales_order_submit':
        so_name = data.get('name')
        
        # Create project
        frappe.get_doc({
            'doctype': 'Project',
            'project_name': f"SO Installation - {so_name}",
            'sales_order': so_name,
            'expected_start_date': frappe.utils.today()
        }).insert(ignore_permissions=True)
        
        frappe.db.commit()
        
    return {'status': 'processed'}
