"""
V13.6.0 P3 Migration: deploy_raven
Original Server Script: deploy_raven
Type: Whitelisted API
"""

import frappe
import os

@frappe.whitelist()
def deploy_raven():
    """Deploy Raven - sends HUP signal to gunicorn"""
    frappe.enqueue(
        'frappe.utils.execute_in_shell',
        cmd='kill -HUP $(cat /home/frappe/frappe-bench/config/gunicorn.pid 2>/dev/null) 2>&1 || echo "pid not found"; ls /home/frappe/frappe-bench/apps/raven_ai_agent/raven_ai_agent/api/account_utils.py 2>&1',
        queue='short'
    )
    frappe.response['message'] = 'HUP signal sent'
