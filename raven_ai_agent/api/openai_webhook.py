"""
V13.6.0 P3 Migration: openai_webhook.handler
Original Server Script: openai_webhook.handler
Type: Whitelisted API
"""

import frappe
import hmac
import hashlib
import requests

import frappe
import hmac
import hashlib
import requests

@frappe.whitelist(allow_guest=True)  # Allow OpenAI to call this
def handler():
    # Security: Verify HMAC signature
    secret = frappe.get_conf().webhook_secret
    signature = frappe.get_request_header("X-Signature")
    payload = frappe.request.get_data()
    
    computed_sig = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(signature, computed_sig):
        frappe.throw("Invalid signature", frappe.AuthenticationError)

    # Process OpenAI request
    data = frappe.parse_json(payload)
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {get_openai_key()}",
            "Content-Type": "application/json"
        },
        json={
            "model": "gpt-4",
            "messages": [{"role": "user", "content": data.get("prompt")}]
        }
    )
    
    return response.json()

def get_openai_key():
    return frappe.get_doc("Third Party API", "OpenAI").get_password("api_key")
