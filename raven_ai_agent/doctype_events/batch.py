"""
V13.6.0 P3 Migration: Batch Raven Channel Creator
Original Server Script: Batch Raven Channel Creator
Type: DocType Event (Batch)
"""

import frappe

# Create Raven channel for each new Batch (bitacora de lote)

batch_name = doc.name
item = doc.item or ""
expiry = doc.expiry_date or ""

# Channel name: batch-LOTEXX (lowercase, sanitized)
channel_name = f"batch-{batch_name.lower().replace(' ', '-')}"

# Check if channel already exists
existing = frappe.db.exists("Raven Channel", {"channel_name": channel_name})
if existing:
    frappe.msgprint(f"Raven channel '{channel_name}' already exists.")
else:
    # Create the channel in AMB-Wellness workspace
    channel = frappe.get_doc({
        "doctype": "Raven Channel",
        "channel_name": channel_name,
        "type": "Public",
        "channel_description": f"Bitacora Lote {batch_name} | Item: {item} | Exp: {expiry}",
        "workspace": "AMB-Wellness"
    })
    channel.insert(ignore_permissions=True)
    
    # Post initial message to the channel
    msg = frappe.get_doc({
        "doctype": "Raven Message",
        "channel_id": channel.name,
        "text": f"Lote **{batch_name}** creado.\nItem: {item}\nExpiry: {expiry}\nEste canal es la bitacora del lote.",
        "message_type": "Text"
    })
    msg.insert(ignore_permissions=True)
    
    frappe.msgprint(f"Canal Raven '{channel_name}' creado para lote {batch_name}")
