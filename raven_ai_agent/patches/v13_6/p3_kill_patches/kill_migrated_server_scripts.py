# -*- coding: utf-8 -*-
# ==========================================================
# raven_ai_agent.patches.v13_6.p3_kill_patches.kill_migrated_server_scripts
# ==========================================================
# V13.6.0 P3 — Server Script migration kill-patch.
# Deletes Server Script DB rows whose logic has been migrated
# into in-code hooks (doctype_events / api / override_whitelisted_methods)
# OR archived verbatim under docs/legacy/.
#
# Runs automatically on `bench migrate` (listed in patches.txt).
# Pre-kill backups live under /tmp/p3-artifacts/ (full Frappe
# backup + server_scripts_full_dump.json + per-row body files).
# ==========================================================
import frappe


def execute():
    scripts_to_delete = [
        "sales_order_webhook.handler",
        "openai_webhook.handler",
        "Sales Order Webhook Handler",
        "/api/method/raven_webhook_handler.handle",
        "Raven Webhook Handler Script",
        "pdf_to_erpnext_processor",
        "Raven Channel Permission Patch - Startup",
        "Raven Channel Permission Patch",
        "Raven Channel Permission Fix",
        "Batch Raven Channel Creator",
        "deploy_raven",
        "Triggers Script",
        "Sales Order PDF Processor",
        "Raven Channel Permission Patch - Global",
    ]

    deleted = 0
    missing = 0
    failed  = 0
    for script_name in scripts_to_delete:
        try:
            frappe.delete_doc("Server Script", script_name, force=True)
            frappe.db.commit()
            print(f"OK     deleted  : {script_name}")
            deleted += 1
        except frappe.DoesNotExistError:
            print(f"SKIP   not found : {script_name}")
            missing += 1
        except Exception as e:
            print(f"FAIL             : {script_name} -> {e}")
            failed += 1

    total = len(scripts_to_delete)
    print(f"P3 kill-patch (raven_ai_agent): total={total} deleted={deleted} missing={missing} failed={failed}")
