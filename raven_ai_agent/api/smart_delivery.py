"""
Smart Delivery Module — Split from workflows.py
Phase 2: Optimization

Contains delivery-related intelligence:
- Auto batch assignment (FIFO by expiry)
- Preflight delivery check (stock/batch/QI warnings)
- Error suggestion engine for delivery failures

These were previously embedded in workflows.py (lines 100-253).
"""
import frappe
from typing import Dict, List, Optional
from collections import defaultdict
from frappe.utils import flt


# =============================================================================
# AUTO-ASSIGN BATCHES (FIFO by expiry)
# ERPNext v16: Uses Batch.batch_qty (Serial and Batch Bundle model)
# =============================================================================

def auto_assign_batches(dn_doc) -> Dict:
    """Auto-assign batch numbers to DN items that require them (FIFO by expiry).
    
    For items with has_batch_no=1, finds the best available batch in the
    target warehouse using FIFO (earliest expiry first) and assigns it.
    
    Returns:
        dict with 'assigned' count and 'issues' list
    """
    # Use cache for item metadata lookups
    try:
        from raven_ai_agent.api.cache_layer import get_item_meta
    except ImportError:
        get_item_meta = None
    
    items_needing_batch = []
    for item in dn_doc.items:
        if item.batch_no:
            continue
        
        if get_item_meta:
            item_meta = get_item_meta(item.item_code)
        else:
            item_meta = frappe.get_cached_value("Item", item.item_code,
                ["has_batch_no", "has_serial_no"], as_dict=True)
        
        if item_meta and item_meta.get("has_batch_no"):
            items_needing_batch.append(item)
    
    if not items_needing_batch:
        return {"assigned": 0, "issues": []}
    
    assigned = 0
    issues = []
    
    # Group by (item_code, warehouse) for efficient batch lookup
    groups = defaultdict(list)
    for item in items_needing_batch:
        key = (item.item_code, item.warehouse)
        groups[key].append(item)
    
    for (item_code, warehouse), items in groups.items():
        total_needed = sum(flt(it.qty) for it in items)
        
        # Find available batches with stock (FIFO by expiry)
        # Use cache if available (30s TTL)
        try:
            from raven_ai_agent.api.cache_layer import get_available_batches
            batches = get_available_batches(item_code, warehouse)
        except ImportError:
            batches = frappe.db.sql("""
                SELECT name as batch_no, batch_qty, expiry_date
                FROM `tabBatch`
                WHERE item = %s
                  AND disabled = 0
                  AND batch_qty > 0
                  AND (expiry_date IS NULL OR expiry_date >= CURDATE())
                ORDER BY COALESCE(expiry_date, '9999-12-31') ASC
            """, (item_code,), as_dict=True)
        
        if not batches:
            issues.append(
                f"No batch with stock for {item_code} in {warehouse} (need {total_needed})"
            )
            continue
        
        batch_idx = 0
        remaining_in_batch = flt(batches[0].get("batch_qty", 0)) if batches else 0
        
        for item in items:
            qty_needed = flt(item.qty)
            while batch_idx < len(batches) and remaining_in_batch <= 0:
                batch_idx += 1
                if batch_idx < len(batches):
                    remaining_in_batch = flt(batches[batch_idx].get("batch_qty", 0))
            
            if batch_idx < len(batches):
                item.batch_no = batches[batch_idx]["batch_no"]
                item.use_serial_batch_fields = 1
                remaining_in_batch -= qty_needed
                assigned += 1
            else:
                issues.append(
                    f"Insufficient batch stock for {item_code} row {item.idx}"
                )
    
    return {"assigned": assigned, "issues": issues}


# =============================================================================
# PREFLIGHT DELIVERY CHECK
# =============================================================================

def preflight_delivery_check(so_doc) -> Dict:
    """Pre-flight validation before creating DN.
    Checks stock availability, batch requirements, QI requirements.
    
    Returns:
        dict with 'warnings' and 'blockers' lists
    """
    try:
        from raven_ai_agent.api.cache_layer import get_item_meta, get_available_batches
        use_cache = True
    except ImportError:
        use_cache = False
    
    warnings = []
    blockers = []
    
    for item in so_doc.items:
        item_code = item.item_code
        qty_needed = flt(item.qty) - flt(item.delivered_qty)
        if qty_needed <= 0:
            continue
        
        if use_cache:
            item_meta = get_item_meta(item_code)
        else:
            item_meta = frappe.get_cached_value("Item", item_code,
                ["has_batch_no", "has_serial_no",
                 "inspection_required_before_delivery"], as_dict=True)
        
        if not item_meta:
            continue
        
        if item_meta.get("inspection_required_before_delivery"):
            warnings.append(f"Item {item_code}: Quality Inspection required before delivery")
        
        warehouse = item.warehouse or "FG to Sell Warehouse - AMB-W"
        if item_meta.get("has_batch_no"):
            if use_cache:
                batches = get_available_batches(item_code, warehouse)
                available = sum(flt(b.get("batch_qty", 0)) for b in batches)
            else:
                batch_stock = frappe.db.sql("""
                    SELECT COALESCE(SUM(batch_qty), 0) as total_qty
                    FROM `tabBatch`
                    WHERE item = %s
                      AND disabled = 0
                      AND (expiry_date IS NULL OR expiry_date >= CURDATE())
                """, (item_code,), as_dict=True)
                available = flt(batch_stock[0].total_qty) if batch_stock else 0
            
            if available < qty_needed:
                warnings.append(
                    f"Item {item_code}: Batch stock {available} < needed {qty_needed} in {warehouse}"
                )
        else:
            bin_qty = frappe.db.get_value("Bin",
                {"item_code": item_code, "warehouse": warehouse}, "actual_qty") or 0
            if flt(bin_qty) < qty_needed:
                warnings.append(
                    f"Item {item_code}: Stock {bin_qty} < needed {qty_needed} in {warehouse}"
                )
    
    return {"warnings": warnings, "blockers": blockers}


# =============================================================================
# ERROR SUGGESTION ENGINE
# =============================================================================

# Pattern: (error substring, suggestion)
ERROR_PATTERNS = [
    (
        "Serial No / Batch No",
        "Item requires batch tracking. The agent will auto-assign batches using FIFO. "
        "Ensure stock exists in a valid batch: @ai mfg status"
    ),
    (
        "inspection_required_before_delivery",
        "This item requires Quality Inspection before delivery. "
        "Create a QI record first, or disable the flag on the Item master."
    ),
    (
        "Insufficient Stock",
        "Not enough stock in the target warehouse. Check available batches: "
        "@ai check stock [ITEM_CODE]. Or create a Material Receipt first."
    ),
    (
        "Already exists",
        "A document with this reference already exists (idempotency check). "
        "The operation may have already been completed successfully."
    ),
    (
        "Not permitted",
        "Permission denied. Check that the current user has the correct Role "
        "and Document permissions for this operation."
    ),
    (
        "Closed",
        "The linked document (SO/PO) is marked as Closed. "
        "Re-open it first before creating dependent documents."
    ),
    (
        "Cancelled",
        "Cannot create from a cancelled document. Check the source document status."
    ),
]


def get_error_suggestions(error_message: str) -> List[str]:
    """Analyze an error message and return actionable recovery suggestions."""
    suggestions = []
    error_lower = error_message.lower()
    
    for pattern, suggestion in ERROR_PATTERNS:
        if pattern.lower() in error_lower:
            suggestions.append(suggestion)
    
    if not suggestions:
        suggestions.append(
            "Unexpected error. Check the Error Log in ERPNext for details, "
            "or retry with: @ai [same command]"
        )
    
    return suggestions
