"""
BOM/Work Order Helper Functions — Split from workflows.py
Phase 2: Optimization

Contains BOM automation functions:
- Default operation times and workstations
- BOM validation and auto-fix
- Work order creation from BOM
- Work order diagnosis

These were previously in workflows.py (lines 17-467).
"""
import frappe
import json
from typing import Dict, List, Optional
from frappe.utils import flt


# =============================================================================
# BOM/WORK ORDER DEFAULTS
# =============================================================================

def get_default_operation_time(operation_name: str) -> int:
    """Get default operation time based on operation type."""
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
    """Get default workstation based on operation type."""
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
    """Get default BOM for an item. Uses cache if available."""
    try:
        from raven_ai_agent.api.cache_layer import get_default_bom_cached
        return get_default_bom_cached(item_code)
    except ImportError:
        pass
    
    try:
        bom_list = frappe.get_all("BOM",
            filters={"item": item_code, "is_active": 1},
            fields=["name"],
            order_by="creation desc",
            limit=1)
        return bom_list[0].name if bom_list else None
    except Exception:
        return None


def get_default_fg_warehouse() -> str:
    """Get default finished goods warehouse. Uses cache if available."""
    try:
        from raven_ai_agent.api.cache_layer import get_warehouse_defaults
        defaults = get_warehouse_defaults()
        return defaults.get("default_warehouse", "Finished Goods - AW")
    except ImportError:
        default = frappe.db.get_single_value("Stock Settings", "default_warehouse")
        return default or "Finished Goods - AW"


def get_default_wip_warehouse() -> str:
    """Get default work-in-progress warehouse. Uses cache if available."""
    try:
        from raven_ai_agent.api.cache_layer import get_warehouse_defaults
        defaults = get_warehouse_defaults()
        return defaults.get("default_wip_warehouse", "Work In Progress - AW")
    except ImportError:
        default = frappe.db.get_single_value("Manufacturing Settings", "default_wip_warehouse")
        return default or "Work In Progress - AW"


def get_default_scrap_warehouse() -> str:
    """Get default scrap warehouse. Uses cache if available."""
    try:
        from raven_ai_agent.api.cache_layer import get_warehouse_defaults
        defaults = get_warehouse_defaults()
        return defaults.get("default_scrap_warehouse", "Scrap Warehouse - AW")
    except ImportError:
        default = frappe.db.get_single_value("Manufacturing Settings", "default_scrap_warehouse")
        return default or "Scrap Warehouse - AW"


# =============================================================================
# IDEMPOTENCY CHECK
# =============================================================================

def idempotency_check(doctype: str, filters: Dict) -> Optional[str]:
    """Check if a document already exists with the given filters.
    Returns document name if found, None otherwise.
    """
    existing = frappe.get_all(doctype,
        filters=filters,
        fields=["name"],
        limit=1)
    return existing[0].name if existing else None


# =============================================================================
# BOM VALIDATION AND AUTO-FIX
# =============================================================================

@frappe.whitelist()
def validate_and_fix_bom(bom_name: str, auto_fix: bool = True) -> Dict:
    """Validates and fixes BOM operation times and workstation assignments.
    
    Based on actual production errors from MFG-WO-02225 type issues.
    """
    try:
        bom = frappe.get_doc("BOM", bom_name)
        issues = []
        fixes = []
        
        # Check operations
        if hasattr(bom, "operations") and bom.operations:
            for op in bom.operations:
                if not op.time_in_mins or op.time_in_mins <= 0:
                    default_time = get_default_operation_time(op.operation)
                    issues.append(f"Operation '{op.operation}' has no time set")
                    if auto_fix:
                        op.time_in_mins = default_time
                        fixes.append(f"Set '{op.operation}' time to {default_time} min")
                
                if not op.workstation:
                    default_ws = get_default_workstation(op.operation)
                    issues.append(f"Operation '{op.operation}' has no workstation")
                    if auto_fix:
                        op.workstation = default_ws
                        fixes.append(f"Set '{op.operation}' workstation to {default_ws}")
        
        if auto_fix and fixes:
            bom.save(ignore_permissions=True)
            frappe.db.commit()
        
        return {
            "success": True,
            "bom": bom_name,
            "issues": issues,
            "fixes": fixes,
            "message": f"Found {len(issues)} issues, applied {len(fixes)} fixes"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def create_work_order_from_bom(bom_name: str, quantity: float = None,
                                production_item: str = None) -> Dict:
    """Create a Work Order from a BOM."""
    try:
        bom = frappe.get_doc("BOM", bom_name)
        
        if bom.docstatus != 1:
            return {"success": False, "error": f"BOM {bom_name} is not submitted."}
        
        item = production_item or bom.item
        qty = quantity or bom.quantity or 1
        
        wo = frappe.new_doc("Work Order")
        wo.production_item = item
        wo.bom_no = bom_name
        wo.qty = qty
        wo.company = bom.company
        wo.fg_warehouse = get_default_fg_warehouse()
        wo.wip_warehouse = get_default_wip_warehouse()
        wo.scrap_warehouse = get_default_scrap_warehouse()
        wo.use_multi_level_bom = 0
        
        wo.insert(ignore_permissions=True)
        frappe.db.commit()
        
        return {
            "success": True,
            "wo_name": wo.name,
            "message": f"Work Order {wo.name} created for {item} qty {qty}"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def diagnose_and_fix_work_order(work_order_name: str) -> Dict:
    """Diagnose common issues with a Work Order and suggest/apply fixes."""
    try:
        wo = frappe.get_doc("Work Order", work_order_name)
        issues = []
        suggestions = []
        
        # Check BOM
        if not wo.bom_no:
            issues.append("No BOM linked")
            suggestions.append("Set a valid BOM: @ai fix wo [WO_NAME] bom [BOM_NAME]")
        elif not frappe.db.exists("BOM", wo.bom_no):
            issues.append(f"BOM {wo.bom_no} does not exist")
        
        # Check item
        if not frappe.db.exists("Item", wo.production_item):
            issues.append(f"Production item {wo.production_item} does not exist")
        
        # Check warehouses
        if not wo.fg_warehouse:
            issues.append("No FG warehouse set")
            suggestions.append(f"Default: {get_default_fg_warehouse()}")
        if not wo.wip_warehouse:
            issues.append("No WIP warehouse set")
            suggestions.append(f"Default: {get_default_wip_warehouse()}")
        
        # Check quantity
        if flt(wo.qty) <= 0:
            issues.append("Quantity is zero or negative")
        
        # Check status
        if wo.docstatus == 2:
            issues.append("Work Order is cancelled")
        
        return {
            "success": True,
            "wo_name": work_order_name,
            "status": wo.status,
            "docstatus": wo.docstatus,
            "issues": issues,
            "suggestions": suggestions,
            "message": f"Diagnosis: {len(issues)} issues found"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
