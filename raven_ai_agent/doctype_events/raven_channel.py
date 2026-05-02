"""
V13.6.0 P3 Migration: Raven Channel Permission Patch
Original Server Script: Raven Channel Permission Patch
Type: DocType Event (Raven Channel)
"""

import frappe


# Parche de permisos para Raven Channels
import frappe

def before_insert(doc, method):
    # Este script se ejecuta antes de insertar un canal
    # El parche real está en frappe.realtime.has_permission
    pass

