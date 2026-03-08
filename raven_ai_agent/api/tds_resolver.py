"""
TDS (Technical Data Sheet) Resolution Module — Split from workflows.py
Phase 2: Optimization

Contains TDS-to-BOM mapping logic:
- Get TDS mapping for sales items
- Resolve production items from TDS
- Create Work Orders using TDS mappings

These were previously in workflows.py (lines 1241-1601).
"""
import frappe
import json
from typing import Dict, List, Optional
from frappe.utils import flt


# =============================================================================
# TDS ITEM MAPPING
# =============================================================================

def get_tds_for_sales_item(sales_item: str, customer: str = None) -> Optional[Dict]:
    """Get TDS mapping for a sales item.
    
    Looks up Item Variant Attribute or custom TDS Link to find the
    production item and appropriate BOM for manufacturing.
    
    Uses cache for repeated lookups.
    """
    # Try cache first
    try:
        from raven_ai_agent.api.cache_layer import (
            get_tds_mapping_cached, set_tds_mapping_cache
        )
        cached = get_tds_mapping_cached(sales_item, customer)
        if cached is not None:
            return cached
        use_cache = True
    except ImportError:
        use_cache = False
    
    # Look for TDS document linked to item
    tds_list = frappe.get_all("Item",
        filters={"name": sales_item},
        fields=["name", "item_name", "variant_of", "has_variants"])
    
    if not tds_list:
        return None
    
    item = tds_list[0]
    result = {
        "sales_item": sales_item,
        "item_name": item.item_name,
        "variant_of": item.variant_of,
        "has_variants": item.has_variants,
    }
    
    # Resolve production item
    production_item = get_production_item_from_tds(sales_item, customer)
    if production_item:
        result["production_item"] = production_item
        result["bom"] = get_bom_for_production_item(production_item)
    
    # Cache the result
    if use_cache:
        set_tds_mapping_cache(sales_item, customer, result)
    
    return result


def get_production_item_from_tds(sales_item: str, customer: str = None) -> Optional[str]:
    """Get production item code from TDS/variant relationship."""
    # If item has a variant_of, the template is likely the production item
    variant_of = frappe.db.get_value("Item", sales_item, "variant_of")
    if variant_of:
        return variant_of
    
    # Check if this item itself has an active BOM
    has_bom = frappe.db.exists("BOM", {"item": sales_item, "is_active": 1})
    if has_bom:
        return sales_item
    
    return None


def get_bom_for_production_item(production_item: str) -> Optional[str]:
    """Get the best BOM for a production item.
    
    Priority:
    1. Default BOM (is_default=1)
    2. Most recently created active BOM
    """
    try:
        from raven_ai_agent.api.cache_layer import get_default_bom_cached
        cached = get_default_bom_cached(production_item)
        if cached:
            return cached
    except ImportError:
        pass
    
    # Try default BOM first
    default_bom = frappe.get_all("BOM",
        filters={"item": production_item, "is_active": 1, "is_default": 1},
        fields=["name"],
        limit=1)
    if default_bom:
        return default_bom[0].name
    
    # Fall back to most recent active BOM
    any_bom = frappe.get_all("BOM",
        filters={"item": production_item, "is_active": 1},
        fields=["name"],
        order_by="creation desc",
        limit=1)
    return any_bom[0].name if any_bom else None


def resolve_tds_bom(sales_item: str, customer: str = None) -> Dict:
    """Full TDS resolution: sales item -> production item -> BOM."""
    tds = get_tds_for_sales_item(sales_item, customer)
    if not tds:
        return {
            "success": False,
            "error": f"No TDS mapping found for '{sales_item}'"
        }
    
    return {
        "success": True,
        "sales_item": sales_item,
        "production_item": tds.get("production_item"),
        "bom": tds.get("bom"),
        "item_name": tds.get("item_name"),
    }


# =============================================================================
# WORK ORDER CREATION FROM TDS
# =============================================================================

def create_work_order_from_tds(sales_item: str, quantity: float,
                                customer: str = None,
                                sales_order: str = None) -> Dict:
    """Create a Work Order using TDS resolution."""
    resolution = resolve_tds_bom(sales_item, customer)
    if not resolution.get("success"):
        return resolution
    
    production_item = resolution.get("production_item")
    bom = resolution.get("bom")
    
    if not production_item:
        return {"success": False, "error": f"No production item resolved for '{sales_item}'"}
    if not bom:
        return {"success": False, "error": f"No active BOM found for '{production_item}'"}
    
    from raven_ai_agent.api.bom_helpers import (
        get_default_fg_warehouse, get_default_wip_warehouse
    )
    
    try:
        wo = frappe.new_doc("Work Order")
        wo.production_item = production_item
        wo.bom_no = bom
        wo.qty = quantity
        wo.company = frappe.db.get_value("BOM", bom, "company")
        wo.fg_warehouse = get_default_fg_warehouse()
        wo.wip_warehouse = get_default_wip_warehouse()
        wo.use_multi_level_bom = 0
        
        if sales_order:
            wo.sales_order = sales_order
        
        wo.insert(ignore_permissions=True)
        frappe.db.commit()
        
        return {
            "success": True,
            "wo_name": wo.name,
            "production_item": production_item,
            "bom": bom,
            "qty": quantity,
            "message": f"Work Order {wo.name} created via TDS resolution"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_work_orders_from_sales_order_with_tds(so_name: str) -> Dict:
    """Create Work Orders for all items in a Sales Order using TDS mapping."""
    try:
        so = frappe.get_doc("Sales Order", so_name)
        if so.docstatus != 1:
            return {"success": False, "error": f"Sales Order '{so_name}' must be submitted."}
        
        results = []
        errors = []
        
        for item in so.items:
            result = create_work_order_from_tds(
                sales_item=item.item_code,
                quantity=item.qty,
                customer=so.customer,
                sales_order=so_name
            )
            if result.get("success"):
                results.append(result)
            else:
                errors.append(f"{item.item_code}: {result.get('error')}")
        
        return {
            "success": len(results) > 0,
            "created": len(results),
            "errors": errors,
            "work_orders": results,
            "message": f"Created {len(results)} WOs from SO {so_name}"
            + (f", {len(errors)} errors" if errors else "")
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# API ENDPOINTS (maintaining backward compatibility)
# =============================================================================

@frappe.whitelist()
def api_resolve_tds_bom(sales_item: str, customer: str = None) -> str:
    return json.dumps(resolve_tds_bom(sales_item, customer))

@frappe.whitelist()
def api_create_work_order_from_tds(sales_item: str, quantity: float,
                                    customer: str = None) -> str:
    return json.dumps(create_work_order_from_tds(sales_item, float(quantity), customer))

@frappe.whitelist()
def api_create_work_orders_from_so_with_tds(so_name: str) -> str:
    return json.dumps(create_work_orders_from_sales_order_with_tds(so_name))
