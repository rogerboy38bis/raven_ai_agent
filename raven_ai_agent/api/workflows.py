"""
ERPNext Workflow Operations — Backward Compatibility Shim
Phase 2: Optimization

This file maintains backward compatibility for all existing imports and
API endpoints. The actual implementation has been split into:
- bom_helpers.py     (BOM/WO defaults, validation, creation)
- smart_delivery.py  (batch assignment, preflight, error suggestions)
- smart_invoice.py   (Mexico CFDI resolution)
- tds_resolver.py    (TDS-to-BOM mapping)
- cache_layer.py     (Redis caching layer)
- queue_handlers.py  (background job queue)

All @frappe.whitelist() endpoints are preserved here for API compatibility.
Internal code should import directly from the new modules.
"""
import frappe
import json
from typing import Dict, List, Optional
from frappe.utils import nowdate, add_days, flt
from datetime import datetime


# =============================================================================
# RE-EXPORTS: BOM/WORK ORDER HELPERS
# =============================================================================

from raven_ai_agent.api.bom_helpers import (
    get_default_operation_time,
    get_default_workstation,
    get_default_bom_for_item,
    get_default_fg_warehouse,
    get_default_wip_warehouse,
    get_default_scrap_warehouse,
    idempotency_check,
    validate_and_fix_bom,
    create_work_order_from_bom,
    diagnose_and_fix_work_order,
)


# =============================================================================
# RE-EXPORTS: SMART DELIVERY
# =============================================================================

from raven_ai_agent.api.smart_delivery import (
    auto_assign_batches as _auto_assign_batches,
    preflight_delivery_check as _preflight_delivery_check,
    get_error_suggestions as _get_error_suggestions,
)


# =============================================================================
# RE-EXPORTS: SMART INVOICE
# =============================================================================

from raven_ai_agent.api.smart_invoice import (
    resolve_mx_cfdi_fields as _resolve_mx_cfdi_fields,
)


# =============================================================================
# RE-EXPORTS: TDS RESOLVER
# =============================================================================

from raven_ai_agent.api.tds_resolver import (
    get_tds_for_sales_item,
    get_production_item_from_tds,
    get_bom_for_production_item,
    resolve_tds_bom,
    create_work_order_from_tds,
    create_work_orders_from_sales_order_with_tds,
    api_resolve_tds_bom,
    api_create_work_order_from_tds,
    api_create_work_orders_from_so_with_tds,
)


# =============================================================================
# WORKFLOW EXECUTOR CLASS
# (Kept in this file for now — to be further split in Phase 3)
# =============================================================================

class WorkflowExecutor:
    """Orchestrates the complete quotation-to-invoice workflow.
    
    Pipeline Steps:
        0: Quotation (truth source)
        1-2: Manufacturing (WO + Stock Entry)
        3: Sales Order Submit
        4-5: Sales WO + Stock Entry
        6: Delivery Note (with smart batch assignment)
        7: Sales Invoice (with CFDI resolution)
        8: Payment Entry
    """

    def __init__(self, user: str = None, dry_run: bool = False):
        self.user = user or frappe.session.user
        self.dry_run = dry_run
        self.site_name = frappe.local.site

    def get_by_folio(self, doctype: str, folio: str) -> Optional[str]:
        existing = frappe.get_all(doctype, filters={"name": ["like", f"%{folio}%"]}, limit=1)
        return existing[0].name if existing else None

    def get_or_create(self, doctype: str, folio: str, create_fn) -> Dict:
        existing = self.get_by_folio(doctype, folio)
        if existing:
            return {
                "success": True,
                "name": existing,
                "already_existed": True,
                "message": f"{doctype} {existing} already exists",
                "link": self.make_link(doctype, existing)
            }
        return create_fn()

    def make_link(self, doctype: str, name: str) -> str:
        slug = doctype.lower().replace(" ", "-")
        return f"[{name}](https://{self.site_name}/app/{slug}/{name})"

    # --- Quotation Operations ---

    def submit_quotation(self, quotation_name: str, confirm: bool = False) -> Dict:
        try:
            doc = frappe.get_doc("Quotation", quotation_name)
            if doc.docstatus == 1:
                return {"success": True, "name": quotation_name,
                        "message": f"Quotation already submitted",
                        "link": self.make_link("Quotation", quotation_name)}
            if not confirm and not self.dry_run:
                return {"success": True, "preview": True,
                        "message": f"Ready to submit {quotation_name}. Use ! to confirm."}
            if self.dry_run:
                return {"success": True, "dry_run": True,
                        "message": f"[DRY RUN] Would submit {quotation_name}"}
            doc.submit()
            frappe.db.commit()
            return {"success": True, "name": quotation_name,
                    "message": f"Quotation {quotation_name} submitted",
                    "link": self.make_link("Quotation", quotation_name)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_quotation_details(self, quotation_name: str) -> Dict:
        try:
            doc = frappe.get_doc("Quotation", quotation_name)
            return {
                "success": True,
                "name": doc.name,
                "status": doc.status,
                "docstatus": doc.docstatus,
                "customer": doc.party_name,
                "total": doc.grand_total,
                "items": [{
                    "item_code": i.item_code,
                    "qty": i.qty,
                    "rate": i.rate,
                    "amount": i.amount
                } for i in doc.items]
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # --- Sales Order Operations ---

    def create_sales_order_from_quotation(self, quotation_name: str, confirm: bool = False) -> Dict:
        try:
            qtn = frappe.get_doc("Quotation", quotation_name)
            if qtn.docstatus != 1:
                return {"success": False, "error": f"Quotation must be submitted first."}
            
            existing = idempotency_check("Sales Order", {"quotation": quotation_name, "docstatus": ["!=", 2]})
            if existing:
                return {"success": True, "name": existing, "already_existed": True,
                        "message": f"Sales Order {existing} already exists for this quotation",
                        "link": self.make_link("Sales Order", existing)}
            
            if not confirm and not self.dry_run:
                return {"success": True, "preview": True,
                        "message": f"Ready to create SO from {quotation_name}. Use ! to confirm."}
            if self.dry_run:
                return {"success": True, "dry_run": True,
                        "message": f"[DRY RUN] Would create SO from {quotation_name}"}
            
            from erpnext.selling.doctype.quotation.quotation import make_sales_order
            so = make_sales_order(quotation_name)
            so.delivery_date = add_days(nowdate(), 30)
            so.insert(ignore_permissions=True)
            frappe.db.commit()
            
            return {"success": True, "name": so.name,
                    "message": f"Sales Order {so.name} created",
                    "link": self.make_link("Sales Order", so.name)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def submit_sales_order(self, so_name: str, confirm: bool = False) -> Dict:
        try:
            doc = frappe.get_doc("Sales Order", so_name)
            if doc.docstatus == 1:
                return {"success": True, "name": so_name,
                        "message": "Sales Order already submitted",
                        "link": self.make_link("Sales Order", so_name)}
            if not confirm and not self.dry_run:
                return {"success": True, "preview": True,
                        "message": f"Ready to submit {so_name}. Use ! to confirm."}
            if self.dry_run:
                return {"success": True, "dry_run": True,
                        "message": f"[DRY RUN] Would submit {so_name}"}
            doc.submit()
            frappe.db.commit()
            return {"success": True, "name": so_name,
                    "message": f"Sales Order {so_name} submitted",
                    "link": self.make_link("Sales Order", so_name)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # --- Delivery Note Operations (with Smart features) ---

    def create_delivery_note_from_sales_order(self, so_name: str, confirm: bool = False) -> Dict:
        try:
            so = frappe.get_doc("Sales Order", so_name)
            if so.docstatus != 1:
                return {"success": False, "error": "Sales Order must be submitted."}
            
            # Preflight check (always run, even for execute mode)
            preflight = _preflight_delivery_check(so)
            
            if not confirm and not self.dry_run:
                msg = f"Ready to create DN from {so_name}."
                if preflight["warnings"]:
                    msg += "\n\nWarnings:\n" + "\n".join(f"  - {w}" for w in preflight["warnings"])
                if preflight["blockers"]:
                    msg += "\n\nBlockers:\n" + "\n".join(f"  - {b}" for b in preflight["blockers"])
                    return {"success": False, "blockers": preflight["blockers"], "message": msg}
                msg += "\n\nUse ! to confirm."
                return {"success": True, "preview": True, "message": msg,
                        "warnings": preflight["warnings"]}
            
            if self.dry_run:
                return {"success": True, "dry_run": True,
                        "message": f"[DRY RUN] Would create DN from {so_name}",
                        "warnings": preflight["warnings"]}
            
            from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note
            dn = make_delivery_note(so_name)
            dn.insert(ignore_permissions=True)
            
            # Smart: Auto-assign batches (SBB for v16)
            batch_result = _auto_assign_batches(dn)
            if batch_result["assigned"] > 0:
                dn.save(ignore_permissions=True)
            
            # Auto-submit DN when executed with ! prefix (confirm=True)
            dn_status = "Draft"
            submit_note = ""
            if confirm and not batch_result.get("issues"):
                try:
                    dn.submit()
                    dn_status = "Submitted"
                except Exception as submit_err:
                    submit_note = f"\n⚠️ DN created but auto-submit failed: {str(submit_err)[:200]}"
                    frappe.logger().warning(f"[Delivery] Auto-submit failed for {dn.name}: {submit_err}")
            elif confirm and batch_result.get("issues"):
                submit_note = "\n⚠️ DN left as Draft due to batch assignment issues — review before submitting."
            
            frappe.db.commit()
            
            site_name = frappe.local.site
            msg = f"✅ Delivery Note [{dn.name}](https://{site_name}/app/delivery-note/{dn.name}) created ({dn_status})"
            msg += f"\n  Customer: {so.customer}"
            if batch_result["assigned"] > 0:
                msg += f"\n  Batches auto-assigned: {batch_result['assigned']} items"
            if batch_result["issues"]:
                msg += "\n\nBatch warnings:\n" + "\n".join(f"  - {i}" for i in batch_result["issues"])
            msg += submit_note
            
            return {
                "success": True, "name": dn.name,
                "message": msg,
                "link": self.make_link("Delivery Note", dn.name),
                "batch_result": batch_result
            }
        except Exception as e:
            suggestions = _get_error_suggestions(str(e))
            return {"success": False, "error": str(e), "suggestions": suggestions}

    # --- Invoice Operations (with CFDI) ---

    def create_invoice_from_sales_order(self, so_name: str, confirm: bool = False) -> Dict:
        try:
            so = frappe.get_doc("Sales Order", so_name)
            if so.docstatus != 1:
                return {"success": False, "error": "Sales Order must be submitted."}
            
            if not confirm and not self.dry_run:
                cfdi = _resolve_mx_cfdi_fields(so.customer, so.payment_terms_template)
                return {"success": True, "preview": True,
                        "message": f"Ready to create Invoice from {so_name}.\n"
                                   f"  CFDI: {cfdi['mx_payment_option']} | {cfdi['mx_cfdi_use']}\n"
                                   f"  Payment: {cfdi['mode_of_payment']}\n"
                                   f"Use ! to confirm."}
            if self.dry_run:
                return {"success": True, "dry_run": True,
                        "message": f"[DRY RUN] Would create Invoice from {so_name}"}
            
            # First ensure DN exists and is submitted
            dns = frappe.get_all("Delivery Note Item",
                filters={"against_sales_order": so_name, "docstatus": ["!=", 2]},
                fields=["parent"], group_by="parent")
            
            for dn_ref in dns:
                dn_doc = frappe.get_doc("Delivery Note", dn_ref.parent)
                if dn_doc.docstatus == 0:
                    dn_doc.submit()
                    frappe.db.commit()
            
            # Create invoice from SO
            from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
            si = make_sales_invoice(so_name)
            
            # Apply ALL CFDI fields (mode_of_payment + mx_payment_option + mx_cfdi_use)
            # make_sales_invoice returns a Document — use .update() then setattr()
            # to ensure custom Link fields are set even if not in initial meta
            cfdi = _resolve_mx_cfdi_fields(so.customer, so.payment_terms_template)
            try:
                si.update(cfdi)
            except Exception:
                pass
            for field, value in cfdi.items():
                setattr(si, field, value)
            
            si.insert(ignore_permissions=True)
            frappe.db.commit()
            
            return {
                "success": True, "name": si.name,
                "message": f"Sales Invoice {si.name} created with {cfdi['mx_payment_option']} | {cfdi['mx_cfdi_use']}",
                "link": self.make_link("Sales Invoice", si.name),
                "cfdi": cfdi
            }
        except Exception as e:
            suggestions = _get_error_suggestions(str(e))
            return {"success": False, "error": str(e), "suggestions": suggestions}

    def create_invoice_from_delivery_note(self, dn_name: str, confirm: bool = False) -> Dict:
        try:
            dn = frappe.get_doc("Delivery Note", dn_name)
            if dn.docstatus != 1:
                if dn.docstatus == 0 and confirm:
                    dn.submit()
                    frappe.db.commit()
                else:
                    return {"success": False, "error": "DN must be submitted. Use ! to auto-submit."}
            
            if not confirm and not self.dry_run:
                return {"success": True, "preview": True,
                        "message": f"Ready to create Invoice from DN {dn_name}. Use ! to confirm."}
            
            from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice
            si = make_sales_invoice(dn_name)
            
            # Apply ALL CFDI fields (mode_of_payment + mx_payment_option + mx_cfdi_use)
            cfdi = _resolve_mx_cfdi_fields(dn.customer)
            try:
                si.update(cfdi)
            except Exception:
                pass
            for field, value in cfdi.items():
                setattr(si, field, value)
            
            si.insert(ignore_permissions=True)
            frappe.db.commit()
            
            return {
                "success": True, "name": si.name,
                "message": f"Invoice {si.name} created from DN {dn_name}",
                "link": self.make_link("Sales Invoice", si.name),
                "cfdi": cfdi
            }
        except Exception as e:
            suggestions = _get_error_suggestions(str(e))
            return {"success": False, "error": str(e), "suggestions": suggestions}

    # --- Work Order Operations ---

    def create_work_orders_from_sales_order(self, so_name: str, confirm: bool = False) -> Dict:
        try:
            so = frappe.get_doc("Sales Order", so_name)
            if so.docstatus != 1:
                return {"success": False, "error": "Sales Order must be submitted."}
            
            if not confirm and not self.dry_run:
                return {"success": True, "preview": True,
                        "message": f"Ready to create WOs from {so_name}. Use ! to confirm."}
            if self.dry_run:
                return {"success": True, "dry_run": True,
                        "message": f"[DRY RUN] Would create WOs from {so_name}"}
            
            # Try TDS-aware creation first, fall back to standard
            result = create_work_orders_from_sales_order_with_tds(so_name)
            if result.get("success"):
                return result
            
            # Standard WO creation
            created = []
            for item in so.items:
                bom = get_default_bom_for_item(item.item_code)
                if not bom:
                    continue
                wo = frappe.new_doc("Work Order")
                wo.production_item = item.item_code
                wo.bom_no = bom
                wo.qty = item.qty
                wo.sales_order = so_name
                wo.company = so.company
                wo.fg_warehouse = get_default_fg_warehouse()
                wo.wip_warehouse = get_default_wip_warehouse()
                wo.insert(ignore_permissions=True)
                created.append(wo.name)
            
            frappe.db.commit()
            return {
                "success": len(created) > 0,
                "work_orders": created,
                "message": f"Created {len(created)} Work Orders from {so_name}"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # --- Full Workflow ---

    def complete_workflow_to_invoice(self, quotation_name: str) -> Dict:
        """Execute the complete workflow from quotation to invoice."""
        steps_completed = []
        
        # Step 0: Submit quotation
        result = self.submit_quotation(quotation_name, confirm=True)
        if not result.get("success") and not result.get("already_existed"):
            return result
        steps_completed.append(f"Quotation: {result.get('message', 'OK')}")
        
        # Step 1: Create SO
        result = self.create_sales_order_from_quotation(quotation_name, confirm=True)
        if not result.get("success"):
            return {**result, "steps_completed": steps_completed}
        so_name = result.get("name")
        steps_completed.append(f"Sales Order: {so_name}")
        
        # Step 2: Submit SO
        result = self.submit_sales_order(so_name, confirm=True)
        if not result.get("success"):
            return {**result, "steps_completed": steps_completed}
        steps_completed.append(f"SO Submitted: {so_name}")
        
        # Step 3: Create WOs
        result = self.create_work_orders_from_sales_order(so_name, confirm=True)
        steps_completed.append(f"Work Orders: {result.get('message', 'OK')}")
        
        # Step 4: Create DN
        result = self.create_delivery_note_from_sales_order(so_name, confirm=True)
        if result.get("success"):
            dn_name = result.get("name")
            steps_completed.append(f"Delivery Note: {dn_name}")
            
            # Step 5: Create Invoice
            result = self.create_invoice_from_sales_order(so_name, confirm=True)
            if result.get("success"):
                steps_completed.append(f"Invoice: {result.get('name')}")
        
        return {
            "success": True,
            "steps_completed": steps_completed,
            "message": f"Workflow complete: {len(steps_completed)} steps"
        }


# =============================================================================
# MIGRATION CONVENIENCE FUNCTIONS (backward compat)
# =============================================================================

def validate_migration_prerequisites(quotation_name: str) -> Dict:
    """Validate prerequisites for a migration workflow."""
    try:
        qtn = frappe.get_doc("Quotation", quotation_name)
        issues = []
        if not qtn.items:
            issues.append("Quotation has no items")
        if qtn.docstatus == 2:
            issues.append("Quotation is cancelled")
        for item in qtn.items:
            if not get_default_bom_for_item(item.item_code):
                issues.append(f"No BOM for item {item.item_code}")
        return {
            "success": len(issues) == 0,
            "quotation": quotation_name,
            "issues": issues,
            "message": f"{'Ready' if not issues else f'{len(issues)} issues found'}"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def complete_workflow_to_invoice(quotation_name: str, dry_run: bool = False) -> Dict:
    executor = WorkflowExecutor(dry_run=dry_run)
    return executor.complete_workflow_to_invoice(quotation_name)


def submit_quotation(quotation_name: str) -> Dict:
    return WorkflowExecutor().submit_quotation(quotation_name, confirm=True)

def create_sales_order(quotation_name: str) -> Dict:
    return WorkflowExecutor().create_sales_order_from_quotation(quotation_name, confirm=True)

def create_work_orders(so_name: str) -> Dict:
    return WorkflowExecutor().create_work_orders_from_sales_order(so_name, confirm=True)

def create_delivery_note(so_name: str) -> Dict:
    return WorkflowExecutor().create_delivery_note_from_sales_order(so_name, confirm=True)

def create_invoice(dn_name: str) -> Dict:
    return WorkflowExecutor().create_invoice_from_delivery_note(dn_name, confirm=True)

def batch_migrate(quotation_names: List[str], dry_run: bool = False) -> Dict:
    executor = WorkflowExecutor(dry_run=dry_run)
    results = []
    for qtn in quotation_names:
        result = executor.complete_workflow_to_invoice(qtn)
        results.append({"quotation": qtn, **result})
    return {"success": True, "results": results}


# =============================================================================
# API ENDPOINTS (backward compatibility — must stay in workflows.py)
# =============================================================================

@frappe.whitelist()
def api_complete_workflow(quotation_name: str, dry_run: bool = False) -> str:
    return json.dumps(complete_workflow_to_invoice(quotation_name, dry_run))

@frappe.whitelist()
def api_batch_migrate(quotation_names: str, dry_run: bool = False) -> str:
    names = json.loads(quotation_names) if isinstance(quotation_names, str) else quotation_names
    return json.dumps(batch_migrate(names, dry_run))

@frappe.whitelist()
def api_validate_bom(bom_name: str, auto_fix: bool = True) -> str:
    return json.dumps(validate_and_fix_bom(bom_name, auto_fix))

@frappe.whitelist()
def api_create_work_order(bom_name: str, quantity: float = None) -> str:
    return json.dumps(create_work_order_from_bom(bom_name, quantity))

@frappe.whitelist()
def api_diagnose_work_order(work_order_name: str) -> str:
    return json.dumps(diagnose_and_fix_work_order(work_order_name))
