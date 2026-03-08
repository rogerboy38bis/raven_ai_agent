"""
ERPNext Workflow Operations - Consolidated
Level 2/3 Autonomy - Document Creation & Workflow Transitions

Consolidated from:
- raven_ai_agent/api/workflows.py
- amb_w_tds/api/bom_automation.py (validate_and_fix_bom, create_work_order_from_bom, diagnose_and_fix_work_order)
- amb_w_tds/api/quotation_amb.py (idempotency_check)
"""
import frappe
import json
from typing import Dict, List, Optional
from frappe.utils import nowdate, add_days, flt
from datetime import datetime


# =============================================================================
# BOM/WORK ORDER HELPERS (from amb_w_tds/api/bom_automation.py)
# =============================================================================

def get_default_operation_time(operation_name: str) -> int:
    """Get default operation time based on operation type"""
    operation_times = {
        "Cutting": 15,
        "Assembly": 45,
        "Quality Check": 20,
        "Packaging": 10,
        "Manufacturing": 60,
        "Processing": 30
    }
    return operation_times.get(operation_name, 30)


def get_default_workstation(operation_name: str) -> str:
    """Get default workstation based on operation type"""
    workstations = {
        "Cutting": "Cutting Station",
        "Assembly": "Assembly Line",
        "Quality Check": "QC Station",
        "Packaging": "Packaging Line",
        "Manufacturing": "Assembly Line",
        "Processing": "Processing Unit"
    }
    return workstations.get(operation_name, "Assembly Line")


def get_default_bom_for_item(item_code: str) -> Optional[str]:
    """Get default BOM for an item"""
    try:
        bom_list = frappe.get_all("BOM",
            filters={"item": item_code, "is_active": 1},
            fields=["name"],
            order_by="creation desc",
            limit=1)
        return bom_list[0].name if bom_list else None
    except:
        return None


def get_default_fg_warehouse() -> str:
    """Get default finished goods warehouse"""
    # Try to get from settings first
    default = frappe.db.get_single_value("Stock Settings", "default_warehouse")
    return default or "Finished Goods - AW"


def get_default_wip_warehouse() -> str:
    """Get default work-in-progress warehouse"""
    default = frappe.db.get_single_value("Manufacturing Settings", "default_wip_warehouse")
    return default or "Work In Progress - AW"


def get_default_scrap_warehouse() -> str:
    """Get default scrap warehouse"""
    default = frappe.db.get_single_value("Manufacturing Settings", "default_scrap_warehouse")
    return default or "Scrap Warehouse - AW"


# =============================================================================
# IDEMPOTENCY CHECK (from amb_w_tds/api/quotation_amb.py)
# =============================================================================

def idempotency_check(doctype: str, filters: Dict) -> Optional[str]:
    """
    Check for duplicate documents based on filters.
    Returns document name if exists, None otherwise.
    
    Usage:
        existing = idempotency_check("Quotation", {"custom_folio": "QTN-001"})
        if existing:
            return frappe.get_doc("Quotation", existing)
    """
    return frappe.db.get_value(doctype, filters, "name")


# =============================================================================
# BOM AUTOMATION FUNCTIONS (from amb_w_tds/api/bom_automation.py)
# =============================================================================

@frappe.whitelist()
def validate_and_fix_bom(bom_name: str, auto_fix: bool = True) -> Dict:
    """
    Validates and fixes BOM operation times and workstation assignments.
    Based on actual production errors from MFG-WO-02225 type issues.
    
    Args:
        bom_name: Name of the BOM to validate
        auto_fix: If True, automatically fix issues found
        
    Returns:
        Dict with status, issues found, and fixes applied
    """
    try:
        bom = frappe.get_doc("BOM", bom_name)
        issues = []
        fixes_applied = []
        
        # Fix operation times if missing or invalid
        for operation in bom.operations:
            if not operation.time_in_mins or operation.time_in_mins <= 0:
                issue = f"Operation '{operation.operation}' missing time_in_mins"
                issues.append(issue)
                if auto_fix:
                    default_time = get_default_operation_time(operation.operation)
                    operation.time_in_mins = default_time
                    fix = f"Set {operation.operation} time to {default_time} minutes"
                    fixes_applied.append(fix)
        
        # Fix workstation assignments if missing
        for operation in bom.operations:
            if not operation.workstation or operation.workstation == "":
                issue = f"Operation '{operation.operation}' missing workstation"
                issues.append(issue)
                if auto_fix:
                    default_ws = get_default_workstation(operation.operation)
                    operation.workstation = default_ws
                    fix = f"Set {operation.operation} workstation to {default_ws}"
                    fixes_applied.append(fix)
        
        # Save changes if auto_fix is enabled
        if auto_fix and fixes_applied:
            bom.flags.ignore_permissions = True
            bom.save()
            frappe.db.commit()
        
        return {
            "status": "success",
            "bom_name": bom_name,
            "issues_found": len(issues),
            "fixes_applied": len(fixes_applied),
            "issues": issues,
            "fixes": fixes_applied
        }
    except Exception as e:
        frappe.log_error(f"validate_and_fix_bom error: {str(e)}")
        return {
            "status": "error",
            "message": str(e),
            "bom_name": bom_name
        }


@frappe.whitelist()
def create_work_order_from_bom(bom_name: str, quantity: float = None, production_item: str = None) -> Dict:
    """
    Creates a work order from a BOM with all required fields populated.
    Handles common MFG-WO creation errors.
    
    Args:
        bom_name: BOM to create work order from
        quantity: Override quantity (defaults to BOM quantity)
        production_item: Override production item (defaults to BOM item)
        
    Returns:
        Dict with status and work order details
    """
    try:
        # Get BOM details
        bom = frappe.get_doc("BOM", bom_name)
        
        if not quantity:
            quantity = bom.quantity
        if not production_item:
            production_item = bom.item
        
        # Validate and fix BOM first
        fix_result = validate_and_fix_bom(bom_name, auto_fix=True)
        if fix_result.get("status") == "error":
            return fix_result
        
        # Create work order
        wo_doc = frappe.new_doc("Work Order")
        wo_doc.production_item = production_item
        wo_doc.bom_no = bom_name
        wo_doc.qty = flt(quantity)
        wo_doc.fg_warehouse = get_default_fg_warehouse()
        wo_doc.wip_warehouse = get_default_wip_warehouse()
        wo_doc.scrap_warehouse = get_default_scrap_warehouse()
        
        # Set default values
        wo_doc.planned_start_date = nowdate()
        wo_doc.planned_end_date = add_days(nowdate(), 7)
        wo_doc.company = bom.company or frappe.defaults.get_defaults().get("company") or "AMB Wellness"
        
        # Save
        wo_doc.flags.ignore_permissions = True
        wo_doc.insert()
        frappe.db.commit()
        
        return {
            "success": True,
            "status": "success",
            "work_order": wo_doc.name,
            "bom": bom_name,
            "quantity": quantity,
            "bom_fixes": fix_result.get("fixes", []),
            "message": f"Work Order {wo_doc.name} created successfully",
            "link": f"/app/work-order/{wo_doc.name}"
        }
    except Exception as e:
        frappe.log_error(f"create_work_order_from_bom error: {str(e)}")
        return {
            "success": False,
            "status": "error",
            "message": str(e),
            "bom": bom_name
        }


@frappe.whitelist()
def diagnose_and_fix_work_order(work_order_name: str) -> Dict:
    """
    Comprehensive work order diagnosis and automated fixes.
    Identifies and resolves MFG-WO-02225 type errors.
    
    Args:
        work_order_name: Work order to diagnose
        
    Returns:
        Dict with issues found and fixes applied
    """
    try:
        wo = frappe.get_doc("Work Order", work_order_name)
        issues = []
        fixes = []
        
        # Check BOM validity
        if wo.bom_no:
            try:
                bom = frappe.get_doc("BOM", wo.bom_no)
                if not bom.operations:
                    issues.append("BOM has no operations defined")
                    fixes.append("Add operations to BOM or use default operations")
            except:
                issues.append(f"BOM {wo.bom_no} not found or invalid")
                fixes.append("Update work order with valid BOM or set BOM to blank")
        else:
            issues.append("Work Order has no BOM assigned")
            # Try to find default BOM
            if wo.production_item:
                default_bom = get_default_bom_for_item(wo.production_item)
                if default_bom:
                    wo.bom_no = default_bom
                    fixes.append(f"Assigned default BOM {default_bom} to work order")
        
        # Check required fields
        required_fields = ["production_item", "qty", "fg_warehouse", "wip_warehouse"]
        for field in required_fields:
            if not getattr(wo, field, None):
                issues.append(f"Missing required field: {field}")
        
        # Fix warehouses if missing
        if not wo.fg_warehouse:
            wo.fg_warehouse = get_default_fg_warehouse()
            fixes.append(f"Set fg_warehouse to {wo.fg_warehouse}")
        
        if not wo.wip_warehouse:
            wo.wip_warehouse = get_default_wip_warehouse()
            fixes.append(f"Set wip_warehouse to {wo.wip_warehouse}")
        
        if not wo.scrap_warehouse:
            wo.scrap_warehouse = get_default_scrap_warehouse()
            fixes.append(f"Set scrap_warehouse to {wo.scrap_warehouse}")
        
        # Save fixes
        if fixes:
            wo.flags.ignore_permissions = True
            wo.save()
            frappe.db.commit()
        
        return {
            "success": True,
            "status": "success",
            "work_order": work_order_name,
            "issues": issues,
            "fixes_applied": fixes,
            "total_issues": len(issues),
            "total_fixes": len(fixes)
        }
    except Exception as e:
        frappe.log_error(f"diagnose_and_fix_work_order error: {str(e)}")
        return {
            "success": False,
            "status": "error",
            "message": str(e),
            "work_order": work_order_name
        }


# =============================================================================
# WORKFLOW EXECUTOR CLASS (from raven_ai_agent/api/workflows.py)
# =============================================================================

class WorkflowExecutor:
    """Execute ERPNext workflow operations with confirmation"""
    
    def __init__(self, user: str, dry_run: bool = False):
        self.user = user
        self.site_name = frappe.local.site
        self.dry_run = dry_run
    
    # ========== IDEMPOTENCY HELPERS ==========
    
    def get_by_folio(self, doctype: str, folio: str) -> Optional[str]:
        """Check if document exists by custom_folio (idempotency)"""
        return idempotency_check(doctype, {"custom_folio": folio})
    
    def get_or_create(self, doctype: str, folio: str, create_fn) -> Dict:
        """Idempotent get-or-create pattern"""
        existing = self.get_by_folio(doctype, folio)
        if existing:
            return {
                "status": "fetched",
                "action": "fetched",
                "doctype": doctype,
                "name": existing,
                "custom_folio": folio,
                "link": self.make_link(doctype, existing)
            }
        
        if self.dry_run:
            return {
                "status": "dry_run",
                "action": "would_create",
                "doctype": doctype,
                "custom_folio": folio,
                "message": f"Would create {doctype} with folio {folio}"
            }
        
        result = create_fn()
        if result.get("success"):
            return {
                "status": "created",
                "action": "created",
                **result
            }
        return result
    
    def make_link(self, doctype: str, name: str) -> str:
        """Generate clickable link"""
        slug = doctype.lower().replace(" ", "-")
        return f"https://{self.site_name}/app/{slug}/{name}"
    
    # ========== SUBMIT QUOTATION ==========
    
    def submit_quotation(self, quotation_name: str, confirm: bool = False) -> Dict:
        """Submit a draft quotation"""
        try:
            qtn = frappe.get_doc("Quotation", quotation_name)
            
            if qtn.docstatus == 1:
                return {"success": True, "message": f"✅ Quotation **{quotation_name}** is already submitted."}
            
            if qtn.docstatus == 2:
                return {"success": False, "error": f"Quotation {quotation_name} is Cancelled. Cannot submit."}
            
            if not confirm:
                return {
                    "success": True,
                    "requires_confirmation": True,
                    "preview": f"**Submit Quotation {quotation_name}?**\n\n| Field | Value |\n|-------|-------|\n| Customer | {qtn.party_name} |\n| Total | {qtn.currency} {qtn.grand_total:,.2f} |\n\n⚠️ **Confirm?** Reply: `@ai confirm submit quotation {quotation_name}`"
                }
            
            if qtn.valid_till and str(qtn.valid_till) < nowdate():
                qtn.valid_till = add_days(nowdate(), 30)
            
            qtn.flags.ignore_permissions = True
            qtn.save()
            qtn.submit()
            frappe.db.commit()
            
            return {"success": True, "message": f"✅ Quotation **{quotation_name}** submitted successfully!"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ========== QUOTATION TO SALES ORDER ==========
    
    def get_quotation_details(self, quotation_name: str) -> Dict:
        """Get quotation details for conversion"""
        try:
            doc = frappe.get_doc("Quotation", quotation_name)
            return {
                "success": True,
                "quotation": {
                    "name": doc.name,
                    "customer": doc.party_name,
                    "grand_total": doc.grand_total,
                    "currency": doc.currency,
                    "items": [{
                        "item_code": item.item_code,
                        "item_name": item.item_name,
                        "qty": item.qty,
                        "rate": item.rate,
                        "amount": item.amount,
                        "has_bom": bool(get_default_bom_for_item(item.item_code))
                    } for item in doc.items],
                    "status": doc.status,
                    "link": self.make_link("Quotation", doc.name)
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def create_sales_order_from_quotation(self, quotation_name: str, confirm: bool = False) -> Dict:
        """Convert Quotation to Sales Order"""
        try:
            from erpnext.selling.doctype.quotation.quotation import make_sales_order
            
            qtn = frappe.get_doc("Quotation", quotation_name)
            
            if qtn.docstatus != 1:
                return {"success": False, "error": f"Quotation {quotation_name} must be submitted first (docstatus={qtn.docstatus})"}
            
            # Check for existing SO
            existing_so = frappe.db.get_value("Sales Order Item", {"prevdoc_docname": quotation_name}, "parent")
            if existing_so:
                return {
                    "success": True,
                    "message": f"Sales Order already exists: {existing_so}",
                    "sales_order": existing_so,
                    "link": self.make_link("Sales Order", existing_so)
                }
            
            if not confirm:
                return {
                    "success": True,
                    "requires_confirmation": True,
                    "preview": f"**Create Sales Order from {quotation_name}?**\n\n| Field | Value |\n|-------|-------|\n| Customer | {qtn.party_name} |\n| Total | {qtn.currency} {qtn.grand_total:,.2f} |\n\n⚠️ **Confirm?**"
                }
            
            so = make_sales_order(quotation_name)
            so.delivery_date = add_days(nowdate(), 7)
            
            # Fix Payment Terms - Due Date must be >= Posting Date
            today = nowdate()
            if hasattr(so, 'payment_schedule') and so.payment_schedule:
                for ps in so.payment_schedule:
                    if ps.due_date and str(ps.due_date) < today:
                        ps.due_date = today
            
            # Clear invalid payment terms template if needed
            if so.payment_terms_template:
                if not frappe.db.exists("Payment Terms Template", so.payment_terms_template):
                    so.payment_terms_template = None
            
            so.flags.ignore_permissions = True
            so.insert()
            frappe.db.commit()
            
            return {
                "success": True,
                "message": f"✅ Sales Order **{so.name}** created from Quotation {quotation_name}",
                "sales_order": so.name,
                "link": self.make_link("Sales Order", so.name)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ========== SUBMIT SALES ORDER ==========
    
    def submit_sales_order(self, so_name: str, confirm: bool = False) -> Dict:
        """Submit a Sales Order"""
        try:
            so = frappe.get_doc("Sales Order", so_name)
            
            if so.docstatus == 1:
                return {"success": True, "message": f"✅ Sales Order **{so_name}** is already submitted"}
            
            if so.docstatus == 2:
                return {"success": False, "error": f"Sales Order {so_name} is cancelled and cannot be submitted"}
            
            if not confirm:
                return {
                    "success": True,
                    "requires_confirmation": True,
                    "preview": f"**Submit Sales Order {so_name}?**\n\n  Customer: {so.customer}\n  Total: {so.grand_total:,.2f}\n  Items: {len(so.items)}\n\n⚠️ Say 'confirm' or use `!` prefix to proceed"
                }
            
            so.submit()
            frappe.db.commit()
            
            return {
                "success": True,
                "message": f"✅ Sales Order **{so_name}** submitted successfully!",
                "sales_order": so_name,
                "link": self.make_link("Sales Order", so_name)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ========== WORK ORDER FROM SALES ORDER ==========
    
    def create_work_orders_from_sales_order(self, so_name: str, confirm: bool = False) -> Dict:
        """Create Work Orders for items with BOM in Sales Order"""
        try:
            so = frappe.get_doc("Sales Order", so_name)
            
            items_with_bom = []
            for item in so.items:
                bom = get_default_bom_for_item(item.item_code)
                if bom:
                    items_with_bom.append({
                        "item_code": item.item_code,
                        "qty": item.qty,
                        "bom": bom
                    })
            
            if not items_with_bom:
                return {"success": True, "message": "No items with BOM found in Sales Order", "work_orders": []}
            
            if not confirm:
                items_preview = "\n".join([f"- {i['item_code']}: {i['qty']} units (BOM: {i['bom']})" for i in items_with_bom])
                return {
                    "success": True,
                    "requires_confirmation": True,
                    "preview": f"**Create Work Orders for {so_name}?**\n\n{items_preview}\n\n⚠️ **Confirm?**"
                }
            
            created_wos = []
            for item in items_with_bom:
                result = create_work_order_from_bom(item["bom"], item["qty"], item["item_code"])
                if result.get("success"):
                    # Link to Sales Order
                    wo = frappe.get_doc("Work Order", result["work_order"])
                    wo.sales_order = so_name
                    wo.flags.ignore_permissions = True
                    wo.save()
                    frappe.db.commit()
                    created_wos.append(result)
                else:
                    created_wos.append({"item": item["item_code"], "error": result.get("message")})
            
            return {
                "success": True,
                "message": f"Created {len([w for w in created_wos if w.get('success')])} Work Orders",
                "work_orders": created_wos
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ========== DELIVERY NOTE ==========
    
    def create_delivery_note_from_sales_order(self, so_name: str, confirm: bool = False) -> Dict:
        """Create Delivery Note from Sales Order"""
        try:
            from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note
            
            so = frappe.get_doc("Sales Order", so_name)
            
            if so.docstatus != 1:
                return {"success": False, "error": f"Sales Order must be submitted first"}
            
            # Check for existing DN
            existing_dn = frappe.db.get_value("Delivery Note Item", {"against_sales_order": so_name}, "parent")
            if existing_dn:
                return {
                    "success": True,
                    "message": f"Delivery Note already exists: {existing_dn}",
                    "delivery_note": existing_dn,
                    "link": self.make_link("Delivery Note", existing_dn)
                }
            
            if not confirm:
                return {
                    "success": True,
                    "requires_confirmation": True,
                    "preview": f"**Create Delivery Note from {so_name}?**"
                }
            
            dn = make_delivery_note(so_name)
            dn.flags.ignore_permissions = True
            dn.insert()
            frappe.db.commit()
            
            return {
                "success": True,
                "message": f"✅ Delivery Note **{dn.name}** created",
                "delivery_note": dn.name,
                "link": self.make_link("Delivery Note", dn.name)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ========== SALES INVOICE ==========
    
    def create_invoice_from_sales_order(self, so_name: str, confirm: bool = False) -> Dict:
        """Create Sales Invoice from Sales Order — finds linked DN first.
        
        Flow: SO → find DN → create Invoice from DN
        If no DN exists, prompts to create one first.
        If DN exists but is Draft, submits it first.
        """
        try:
            so = frappe.get_doc("Sales Order", so_name)
            if so.docstatus != 1:
                return {"success": False, "error": f"Sales Order must be submitted first"}
            
            # Find linked Delivery Notes
            dn_items = frappe.get_all("Delivery Note Item",
                filters={"against_sales_order": so_name, "docstatus": ["!=", 2]},
                fields=["parent"],
                group_by="parent")
            
            if not dn_items:
                return {
                    "success": False,
                    "error": (
                        f"No Delivery Note found for {so_name}.\n"
                        f"Create one first: `@ai !delivery from {so_name}`"
                    )
                }
            
            dn_name = dn_items[0].parent
            dn = frappe.get_doc("Delivery Note", dn_name)
            
            # If DN is Draft, submit it first
            if dn.docstatus == 0:
                if not confirm:
                    return {
                        "success": True,
                        "requires_confirmation": True,
                        "preview": (
                            f"**Invoice from {so_name}**\n\n"
                            f"Found DN: {dn_name} (Draft)\n"
                            f"Will submit DN first, then create Sales Invoice.\n\n"
                            f"Use `!invoice from {so_name}` to execute."
                        )
                    }
                # Submit the DN
                dn.submit()
                frappe.db.commit()
            
            # Check for existing invoice
            existing_inv = frappe.db.get_value("Sales Invoice Item",
                {"delivery_note": dn_name, "docstatus": ["!=", 2]}, "parent")
            if existing_inv:
                return {
                    "success": True,
                    "message": (
                        f"Sales Invoice already exists: **{existing_inv}**\n"
                        f"Link: {self.make_link('Sales Invoice', existing_inv)}"
                    ),
                    "invoice": existing_inv,
                    "link": self.make_link("Sales Invoice", existing_inv)
                }
            
            if not confirm:
                return {
                    "success": True,
                    "requires_confirmation": True,
                    "preview": (
                        f"**Create Sales Invoice from {so_name}?**\n\n"
                        f"Delivery Note: {self.make_link('Delivery Note', dn_name)} (Submitted)\n"
                        f"Customer: {so.customer_name}\n"
                        f"Total: {so.grand_total}\n\n"
                        f"Use `!invoice from {so_name}` to execute."
                    )
                }
            
            # Create invoice from DN
            from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice
            inv = make_sales_invoice(dn_name)
            inv.flags.ignore_permissions = True
            inv.insert()
            frappe.db.commit()
            
            return {
                "success": True,
                "message": (
                    f"\u2705 Sales Invoice **{inv.name}** created\n\n"
                    f"  From DN: {self.make_link('Delivery Note', dn_name)}\n"
                    f"  Sales Order: {self.make_link('Sales Order', so_name)}\n"
                    f"  Customer: {so.customer_name}\n"
                    f"  Total: {so.grand_total}\n"
                    f"  Link: {self.make_link('Sales Invoice', inv.name)}"
                ),
                "invoice": inv.name,
                "link": self.make_link("Sales Invoice", inv.name)
            }
        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Sales Order '{so_name}' not found."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def create_invoice_from_delivery_note(self, dn_name: str, confirm: bool = False) -> Dict:
        """Create Sales Invoice from Delivery Note"""
        try:
            from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice
            
            dn = frappe.get_doc("Delivery Note", dn_name)
            
            if dn.docstatus != 1:
                return {"success": False, "error": f"Delivery Note must be submitted first"}
            
            # Check for existing invoice
            existing_inv = frappe.db.get_value("Sales Invoice Item", {"delivery_note": dn_name}, "parent")
            if existing_inv:
                return {
                    "success": True,
                    "message": f"Sales Invoice already exists: {existing_inv}",
                    "invoice": existing_inv,
                    "link": self.make_link("Sales Invoice", existing_inv)
                }
            
            if not confirm:
                return {
                    "success": True,
                    "requires_confirmation": True,
                    "preview": f"**Create Sales Invoice from {dn_name}?**"
                }
            
            inv = make_sales_invoice(dn_name)
            inv.flags.ignore_permissions = True
            inv.insert()
            frappe.db.commit()
            
            return {
                "success": True,
                "message": f"✅ Sales Invoice **{inv.name}** created",
                "invoice": inv.name,
                "link": self.make_link("Sales Invoice", inv.name)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


# =============================================================================
# MODULE-LEVEL CONVENIENCE FUNCTIONS (Sudo Mode - No Confirmation)
# =============================================================================

def validate_migration_prerequisites(quotation_name: str) -> Dict:
    """
    Validate all prerequisites before migration.
    Lessons learned from sandbox testing.
    """
    issues = []
    warnings = []
    
    try:
        qtn = frappe.get_doc("Quotation", quotation_name)
        
        # Check customer
        if not frappe.db.exists("Customer", qtn.party_name):
            issues.append(f"Customer '{qtn.party_name}' does not exist")
        
        # Check items
        for item in qtn.items:
            if not frappe.db.exists("Item", item.item_code):
                issues.append(f"Item '{item.item_code}' does not exist")
            else:
                # Check if item has BOM (for manufacturing)
                bom = get_default_bom_for_item(item.item_code)
                if bom:
                    # Validate BOM
                    bom_check = validate_and_fix_bom(bom, auto_fix=False)
                    if bom_check.get("issues"):
                        warnings.append(f"BOM {bom} has issues (will auto-fix): {bom_check['issues']}")
        
        # Check fiscal year
        from erpnext.accounts.utils import get_fiscal_year
        try:
            get_fiscal_year(nowdate(), company=qtn.company)
        except:
            issues.append(f"No Fiscal Year for {nowdate()} in {qtn.company}")
        
        return {
            "success": True,
            "quotation": quotation_name,
            "can_proceed": len(issues) == 0,
            "issues": issues,
            "warnings": warnings
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def complete_workflow_to_invoice(quotation_name: str, dry_run: bool = False) -> Dict:
    """
    Complete workflow: Quotation → Sales Order → Work Order (if BOM) → Stock Entry → Delivery Note → Invoice
    """
    executor = WorkflowExecutor(user=frappe.session.user, dry_run=dry_run)
    results = {"quotation": quotation_name, "steps": []}
    
    try:
        # Step 1: Submit Quotation
        result = executor.submit_quotation(quotation_name, confirm=True)
        results["steps"].append({"step": "submit_quotation", **result})
        if not result.get("success"):
            return results
        
        # Step 2: Create Sales Order
        result = executor.create_sales_order_from_quotation(quotation_name, confirm=True)
        results["steps"].append({"step": "create_sales_order", **result})
        if not result.get("success") or not result.get("sales_order"):
            return results
        
        so_name = result["sales_order"]
        
        # Step 3: Submit Sales Order
        try:
            so = frappe.get_doc("Sales Order", so_name)
            if so.docstatus == 0:
                so.flags.ignore_permissions = True
                so.submit()
                frappe.db.commit()
                results["steps"].append({"step": "submit_sales_order", "success": True, "sales_order": so_name})
            else:
                results["steps"].append({"step": "submit_sales_order", "success": True, "message": "Already submitted"})
        except Exception as e:
            results["steps"].append({"step": "submit_sales_order", "success": False, "error": str(e)})
            return results
        
        # Step 4: Create Work Orders (if items have BOM)
        result = executor.create_work_orders_from_sales_order(so_name, confirm=True)
        results["steps"].append({"step": "create_work_orders", **result})
        
        # Step 5: Check/Create Stock Entry for items without enough stock
        try:
            so = frappe.get_doc("Sales Order", so_name)
            stock_entries_created = []
            
            for item in so.items:
                # Check available stock
                from erpnext.stock.utils import get_stock_balance
                warehouse = item.warehouse or frappe.db.get_single_value("Stock Settings", "default_warehouse")
                if not warehouse:
                    # Find a leaf warehouse
                    warehouse = frappe.db.get_value("Warehouse", 
                        {"company": so.company, "is_group": 0}, "name")
                
                if warehouse:
                    available = get_stock_balance(item.item_code, warehouse)
                    if available < item.qty:
                        # Create Material Receipt Stock Entry
                        se = frappe.new_doc("Stock Entry")
                        se.stock_entry_type = "Material Receipt"
                        se.company = so.company
                        se.purpose = "Material Receipt"
                        
                        se_item = se.append("items", {})
                        se_item.item_code = item.item_code
                        se_item.qty = item.qty - available
                        se_item.t_warehouse = warehouse
                        se_item.basic_rate = item.rate or 1
                        
                        se.flags.ignore_permissions = True
                        se.insert()
                        se.submit()
                        frappe.db.commit()
                        stock_entries_created.append({
                            "item": item.item_code,
                            "qty": item.qty - available,
                            "stock_entry": se.name
                        })
            
            if stock_entries_created:
                results["steps"].append({
                    "step": "create_stock_entries", 
                    "success": True, 
                    "entries": stock_entries_created
                })
            else:
                results["steps"].append({
                    "step": "create_stock_entries",
                    "success": True,
                    "message": "Sufficient stock available"
                })
        except Exception as e:
            results["steps"].append({"step": "create_stock_entries", "success": False, "error": str(e)})
            # Continue anyway - stock entry is optional
        
        # Step 6: Create Delivery Note
        result = executor.create_delivery_note_from_sales_order(so_name, confirm=True)
        results["steps"].append({"step": "create_delivery_note", **result})
        if not result.get("success") or not result.get("delivery_note"):
            return results
        
        dn_name = result["delivery_note"]
        
        # Step 5: Submit Delivery Note
        dn = frappe.get_doc("Delivery Note", dn_name)
        if dn.docstatus == 0:
            dn.flags.ignore_permissions = True
            dn.submit()
            frappe.db.commit()
            results["steps"].append({"step": "submit_delivery_note", "success": True, "delivery_note": dn_name})
        
        # Step 6: Create Invoice
        result = executor.create_invoice_from_delivery_note(dn_name, confirm=True)
        results["steps"].append({"step": "create_invoice", **result})
        
        results["success"] = True
        results["message"] = f"Workflow complete: {quotation_name} → Invoice"
        return results
        
    except Exception as e:
        results["success"] = False
        results["error"] = str(e)
        return results


# Convenience wrappers
def submit_quotation(quotation_name: str) -> Dict:
    """Submit a quotation (Sudo mode - no confirmation)"""
    return WorkflowExecutor(frappe.session.user).submit_quotation(quotation_name, confirm=True)


def create_sales_order(quotation_name: str) -> Dict:
    """Create Sales Order from Quotation (Sudo mode)"""
    return WorkflowExecutor(frappe.session.user).create_sales_order_from_quotation(quotation_name, confirm=True)


def create_work_orders(so_name: str) -> Dict:
    """Create Work Orders from Sales Order (Sudo mode)"""
    return WorkflowExecutor(frappe.session.user).create_work_orders_from_sales_order(so_name, confirm=True)


def create_delivery_note(so_name: str) -> Dict:
    """Create Delivery Note from Sales Order (Sudo mode)"""
    return WorkflowExecutor(frappe.session.user).create_delivery_note_from_sales_order(so_name, confirm=True)


def create_invoice(dn_name: str) -> Dict:
    """Create Sales Invoice from Delivery Note (Sudo mode)"""
    return WorkflowExecutor(frappe.session.user).create_invoice_from_delivery_note(dn_name, confirm=True)


def batch_migrate(quotation_names: List[str], dry_run: bool = False) -> Dict:
    """Batch migrate multiple quotations"""
    results = []
    for qtn in quotation_names:
        result = complete_workflow_to_invoice(qtn, dry_run=dry_run)
        results.append(result)
    return {"success": True, "results": results}


# =============================================================================
# FRAPPE WHITELISTED API ENDPOINTS
# =============================================================================

@frappe.whitelist()
def api_complete_workflow(quotation_name: str, dry_run: bool = False) -> str:
    """API endpoint for complete workflow"""
    result = complete_workflow_to_invoice(quotation_name, dry_run=bool(dry_run))
    return json.dumps(result)


@frappe.whitelist()
def api_batch_migrate(quotation_names: str, dry_run: bool = False) -> str:
    """API endpoint for batch migration. quotation_names is comma-separated."""
    names = [n.strip() for n in quotation_names.split(",")]
    result = batch_migrate(names, dry_run=bool(dry_run))
    return json.dumps(result)


@frappe.whitelist()
def api_validate_bom(bom_name: str, auto_fix: bool = True) -> str:
    """API endpoint for BOM validation"""
    result = validate_and_fix_bom(bom_name, auto_fix=bool(auto_fix))
    return json.dumps(result)


@frappe.whitelist()
def api_create_work_order(bom_name: str, quantity: float = None) -> str:
    """API endpoint for work order creation from BOM"""
    result = create_work_order_from_bom(bom_name, quantity)
    return json.dumps(result)


@frappe.whitelist()
def api_diagnose_work_order(work_order_name: str) -> str:
    """API endpoint for work order diagnosis"""
    result = diagnose_and_fix_work_order(work_order_name)
    return json.dumps(result)


# =============================================================================
# TDS WORKFLOW INTEGRATION
# Sales Item → TDS Product Specification → Production Item → BOM → Work Order
# =============================================================================

def get_tds_for_sales_item(sales_item: str, customer: str = None) -> Optional[Dict]:
    """
    Find TDS Product Specification for a sales item.
    
    TDS naming patterns supported:
    - Exact: "0308"
    - With hyphen: "0308-CUSTOMER" or "0308-0301"
    - With space: "0308 Customer Name" or "0308 TDS BASE"
    
    Args:
        sales_item: The sales/generic item code (e.g., "0308")
        customer: Optional customer name to find specific TDS
    
    Returns:
        Dict with TDS details or None if not found
    """
    try:
        tds_list = []
        base_filters = {"docstatus": ["!=", 2]}
        
        # Priority 1: Customer-specific TDS (if customer provided)
        if customer:
            # Try "{item}-{customer}" pattern
            filters = {**base_filters, "name": ["like", f"{sales_item}-{customer}%"]}
            tds_list = frappe.get_all(
                "TDS Product Specification", filters=filters,
                fields=["name", "product_item", "workflow_state"],
                order_by="creation desc", limit=1
            )
            if not tds_list:
                # Try "{item} {customer}" pattern
                filters["name"] = ["like", f"{sales_item} {customer}%"]
                tds_list = frappe.get_all(
                    "TDS Product Specification", filters=filters,
                    fields=["name", "product_item", "workflow_state"],
                    order_by="creation desc", limit=1
                )
        
        # Priority 2: Exact match (e.g., "0308")
        if not tds_list:
            tds_list = frappe.get_all(
                "TDS Product Specification",
                filters={**base_filters, "name": sales_item},
                fields=["name", "product_item", "workflow_state"],
                limit=1
            )
        
        # Priority 3: Base/Master TDS (e.g., "0308 TDS BASE", "0308 Base")
        if not tds_list:
            for pattern in [f"{sales_item} TDS%", f"{sales_item} Base%", f"{sales_item} Master%"]:
                tds_list = frappe.get_all(
                    "TDS Product Specification",
                    filters={**base_filters, "name": ["like", pattern]},
                    fields=["name", "product_item", "workflow_state"],
                    order_by="creation desc", limit=1
                )
                if tds_list:
                    break
        
        # Priority 4: Any TDS starting with sales_item
        if not tds_list:
            tds_list = frappe.get_all(
                "TDS Product Specification",
                filters={**base_filters, "name": ["like", f"{sales_item}%"]},
                fields=["name", "product_item", "workflow_state"],
                order_by="creation desc", limit=1
            )
        
        if tds_list:
            tds = tds_list[0]
            return {
                "success": True,
                "tds_name": tds.name,
                "sales_item": sales_item,
                "production_item": tds.product_item,
                "workflow_state": tds.workflow_state
            }
        return None
    except Exception as e:
        frappe.log_error(f"get_tds_for_sales_item error: {str(e)}")
        return None


def get_production_item_from_tds(sales_item: str, customer: str = None) -> Optional[str]:
    """
    Get the production item code from TDS for a given sales item.
    
    Args:
        sales_item: The sales/generic item code
        customer: Optional customer for customer-specific TDS
    
    Returns:
        Production item code or None
    """
    tds = get_tds_for_sales_item(sales_item, customer)
    if tds:
        return tds.get("production_item")
    return None


def get_bom_for_production_item(production_item: str) -> Optional[str]:
    """
    Get the default/active BOM for a production item.
    First checks Item's default_bom, then looks for active BOM.
    
    Args:
        production_item: The production item code
    
    Returns:
        BOM name or None
    """
    try:
        # First check if item has default_bom set
        default_bom = frappe.db.get_value("Item", production_item, "default_bom")
        if default_bom and frappe.db.exists("BOM", {"name": default_bom, "is_active": 1}):
            return default_bom
        
        # Otherwise find active BOM
        bom = frappe.get_all(
            "BOM",
            filters={"item": production_item, "is_active": 1, "docstatus": 1},
            fields=["name"],
            order_by="is_default desc, creation desc",
            limit=1
        )
        return bom[0].name if bom else None
    except:
        return None


def resolve_tds_bom(sales_item: str, customer: str = None) -> Dict:
    """
    Complete TDS → Production Item → BOM resolution.
    
    Args:
        sales_item: The sales/generic item code from Sales Order
        customer: Optional customer for customer-specific TDS
    
    Returns:
        Dict with resolution chain or error
    """
    result = {
        "sales_item": sales_item,
        "customer": customer,
        "tds_name": None,
        "production_item": None,
        "bom": None,
        "success": False
    }
    
    # Step 1: Find TDS
    tds = get_tds_for_sales_item(sales_item, customer)
    if not tds:
        result["error"] = f"No TDS found for sales item '{sales_item}'"
        return result
    
    result["tds_name"] = tds["tds_name"]
    result["production_item"] = tds["production_item"]
    
    # Step 2: Find BOM for production item
    if not result["production_item"]:
        result["error"] = f"TDS '{tds['tds_name']}' has no production item (item_code)"
        return result
    
    bom = get_bom_for_production_item(result["production_item"])
    if not bom:
        result["error"] = f"No active BOM found for production item '{result['production_item']}'"
        result["suggestion"] = "Create BOM from BOM Creator or assign default_bom on Item"
        return result
    
    result["bom"] = bom
    result["success"] = True
    result["message"] = f"Resolved: {sales_item} → TDS:{tds['tds_name']} → {result['production_item']} → BOM:{bom}"
    
    return result


def create_work_order_from_tds(sales_item: str, quantity: float, customer: str = None, 
                                sales_order: str = None) -> Dict:
    """
    Create Work Order using TDS-specified production item and BOM.
    
    This is the key function for the "Parallel Workflow":
    - Sales Order uses generic item (e.g., 0307)
    - Work Order uses specific production item from TDS (e.g., 0307-500/100...)
    
    Args:
        sales_item: The sales/generic item code
        quantity: Production quantity
        customer: Customer for customer-specific TDS lookup
        sales_order: Optional Sales Order to link
    
    Returns:
        Dict with work order details or error
    """
    try:
        # Resolve TDS chain
        resolution = resolve_tds_bom(sales_item, customer)
        if not resolution["success"]:
            return resolution
        
        # Create Work Order with production item and BOM
        result = create_work_order_from_bom(
            bom_name=resolution["bom"],
            quantity=quantity,
            production_item=resolution["production_item"]
        )
        
        if result.get("success") and sales_order:
            # Link to Sales Order
            wo = frappe.get_doc("Work Order", result["work_order"])
            wo.sales_order = sales_order
            wo.flags.ignore_permissions = True
            wo.save()
            frappe.db.commit()
            result["sales_order"] = sales_order
        
        # Add resolution chain to result
        result["tds_resolution"] = resolution
        return result
        
    except Exception as e:
        frappe.log_error(f"create_work_order_from_tds error: {str(e)}")
        return {"success": False, "error": str(e)}


def create_work_orders_from_sales_order_with_tds(so_name: str) -> Dict:
    """
    Create Work Orders for Sales Order items using TDS lookup.
    
    For each item in SO:
    1. Look up TDS by sales item + customer
    2. Get production item from TDS
    3. Get BOM for production item
    4. Create Work Order
    
    Args:
        so_name: Sales Order name
    
    Returns:
        Dict with created work orders and any errors
    """
    try:
        so = frappe.get_doc("Sales Order", so_name)
        customer = so.customer
        
        results = {
            "success": True,
            "sales_order": so_name,
            "customer": customer,
            "work_orders": [],
            "errors": []
        }
        
        for item in so.items:
            # Try TDS resolution first
            resolution = resolve_tds_bom(item.item_code, customer)
            
            if resolution["success"]:
                # Create WO with TDS-specified BOM
                wo_result = create_work_order_from_tds(
                    sales_item=item.item_code,
                    quantity=item.qty,
                    customer=customer,
                    sales_order=so_name
                )
                
                if wo_result.get("success"):
                    results["work_orders"].append({
                        "item": item.item_code,
                        "production_item": resolution["production_item"],
                        "work_order": wo_result["work_order"],
                        "bom": resolution["bom"],
                        "qty": item.qty,
                        "method": "tds"
                    })
                else:
                    results["errors"].append({
                        "item": item.item_code,
                        "error": wo_result.get("error"),
                        "method": "tds"
                    })
            else:
                # Fallback: Try direct BOM lookup on sales item
                direct_bom = get_default_bom_for_item(item.item_code)
                if direct_bom:
                    wo_result = create_work_order_from_bom(direct_bom, item.qty, item.item_code)
                    if wo_result.get("success"):
                        wo = frappe.get_doc("Work Order", wo_result["work_order"])
                        wo.sales_order = so_name
                        wo.flags.ignore_permissions = True
                        wo.save()
                        frappe.db.commit()
                        
                        results["work_orders"].append({
                            "item": item.item_code,
                            "production_item": item.item_code,
                            "work_order": wo_result["work_order"],
                            "bom": direct_bom,
                            "qty": item.qty,
                            "method": "direct"
                        })
                    else:
                        results["errors"].append({
                            "item": item.item_code,
                            "error": wo_result.get("error"),
                            "method": "direct"
                        })
                else:
                    # No TDS, no direct BOM - skip (might be non-manufactured item)
                    results["errors"].append({
                        "item": item.item_code,
                        "error": resolution.get("error", "No BOM found"),
                        "suggestion": resolution.get("suggestion"),
                        "skipped": True
                    })
        
        results["summary"] = {
            "total_items": len(so.items),
            "work_orders_created": len(results["work_orders"]),
            "errors": len([e for e in results["errors"] if not e.get("skipped")]),
            "skipped": len([e for e in results["errors"] if e.get("skipped")])
        }
        
        return results
        
    except Exception as e:
        frappe.log_error(f"create_work_orders_from_sales_order_with_tds error: {str(e)}")
        return {"success": False, "error": str(e)}


# =============================================================================
# TDS API ENDPOINTS
# =============================================================================

@frappe.whitelist()
def api_resolve_tds_bom(sales_item: str, customer: str = None) -> str:
    """API: Resolve TDS chain for a sales item"""
    result = resolve_tds_bom(sales_item, customer)
    return json.dumps(result)


@frappe.whitelist()
def api_create_work_order_from_tds(sales_item: str, quantity: float, 
                                    customer: str = None, sales_order: str = None) -> str:
    """API: Create Work Order using TDS lookup"""
    result = create_work_order_from_tds(sales_item, float(quantity), customer, sales_order)
    return json.dumps(result)


@frappe.whitelist()
def api_create_work_orders_from_so_with_tds(so_name: str) -> str:
    """API: Create Work Orders for Sales Order using TDS lookup"""
    result = create_work_orders_from_sales_order_with_tds(so_name)
    return json.dumps(result)
