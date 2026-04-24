"""
Archived Server Script: Raven Channel Permission Fix

V13.6.0 P3 Server Script Migration
Decision: DEL / archive_enabled_one_shot
Script Type: API
Reference DocType: None
Disabled: 0

Runtime status:
  DO NOT IMPORT. Archive only.
"""

ORIGINAL_SCRIPT = """

import frappe
from frappe.realtime import has_permission

# Guardar función original
original_has_permission = has_permission

def patched_has_permission(doctype, name):
    # Permitir todos los canales de Raven sin verificación
    if doctype == "Raven Channel":
        return True
    return original_has_permission(doctype, name)

# Aplicar parche
frappe.realtime.has_permission = patched_has_permission

print("✅ Parche de permisos de Raven aplicado permanentemente")

"""
