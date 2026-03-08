"""
Redis Caching Layer for Raven AI Agent
Phase 2: Optimization

Provides caching for frequently-accessed ERPNext metadata to reduce
database load and improve response times.

Uses Frappe's built-in Redis cache (frappe.cache) with configurable TTLs.
"""
import frappe
import json
from typing import Dict, List, Optional, Any
from frappe.utils import flt
from frappe.utils.caching import redis_cache


# =============================================================================
# CACHE CONFIGURATION
# =============================================================================

# TTL values in seconds
CACHE_TTL = {
    "item_meta": 600,        # 10 min — item flags (has_batch_no, etc.)
    "bom_default": 300,      # 5 min — default BOM for item
    "warehouse_defaults": 600,  # 10 min — default warehouses from settings
    "batch_stock": 30,       # 30 sec — batch quantities (changes frequently)
    "customer_meta": 300,    # 5 min — customer payment terms, CFDI use
    "tds_mapping": 600,      # 10 min — TDS item mappings
    "settings": 600,         # 10 min — Manufacturing/Stock settings
}

# Cache key prefix to avoid collisions with other apps
CACHE_PREFIX = "rai:"


# =============================================================================
# CACHE HELPERS
# =============================================================================

def _cache_key(namespace: str, identifier: str) -> str:
    """Build a namespaced cache key."""
    return f"{CACHE_PREFIX}{namespace}:{identifier}"


def cache_get(namespace: str, identifier: str) -> Optional[Any]:
    """Get a value from cache. Returns None if not found."""
    key = _cache_key(namespace, identifier)
    val = frappe.cache.get_value(key)
    return val


def cache_set(namespace: str, identifier: str, value: Any, ttl: int = None) -> None:
    """Set a value in cache with optional TTL."""
    key = _cache_key(namespace, identifier)
    ttl = ttl or CACHE_TTL.get(namespace, 300)
    frappe.cache.set_value(key, value, expires_in_sec=ttl)


def cache_delete(namespace: str, identifier: str) -> None:
    """Delete a specific cache entry."""
    key = _cache_key(namespace, identifier)
    frappe.cache.delete_value(key)


def cache_invalidate_namespace(namespace: str) -> None:
    """Invalidate all entries in a namespace (best-effort)."""
    # Frappe doesn't expose pattern-delete easily; we track known keys per namespace
    tracker_key = f"{CACHE_PREFIX}_keys:{namespace}"
    known_keys = frappe.cache.get_value(tracker_key) or []
    for key in known_keys:
        frappe.cache.delete_value(key)
    frappe.cache.delete_value(tracker_key)


def _track_key(namespace: str, identifier: str) -> None:
    """Track a cache key for bulk invalidation."""
    tracker_key = f"{CACHE_PREFIX}_keys:{namespace}"
    known = frappe.cache.get_value(tracker_key) or []
    full_key = _cache_key(namespace, identifier)
    if full_key not in known:
        known.append(full_key)
        frappe.cache.set_value(tracker_key, known, expires_in_sec=3600)


# =============================================================================
# ITEM METADATA CACHE
# =============================================================================

def get_item_meta(item_code: str) -> Optional[Dict]:
    """Get cached item metadata (has_batch_no, has_serial_no, QI flags, etc.).
    
    Returns dict with: has_batch_no, has_serial_no, 
    inspection_required_before_delivery, stock_uom, item_name
    """
    cached = cache_get("item_meta", item_code)
    if cached is not None:
        return cached
    
    meta = frappe.db.get_value("Item", item_code,
        ["has_batch_no", "has_serial_no",
         "inspection_required_before_delivery",
         "stock_uom", "item_name"],
        as_dict=True)
    
    if meta:
        cache_set("item_meta", item_code, meta)
        _track_key("item_meta", item_code)
    
    return meta


def get_default_bom_cached(item_code: str) -> Optional[str]:
    """Get cached default BOM for an item."""
    cached = cache_get("bom_default", item_code)
    if cached is not None:
        return cached if cached != "__NONE__" else None
    
    bom_list = frappe.get_all("BOM",
        filters={"item": item_code, "is_active": 1, "is_default": 1},
        fields=["name"],
        order_by="creation desc",
        limit=1)
    
    result = bom_list[0].name if bom_list else None
    # Cache None as sentinel value to avoid repeated DB lookups
    cache_set("bom_default", item_code, result or "__NONE__")
    _track_key("bom_default", item_code)
    return result


# =============================================================================
# WAREHOUSE DEFAULTS CACHE
# =============================================================================

def get_warehouse_defaults() -> Dict[str, str]:
    """Get cached warehouse defaults from Manufacturing/Stock settings."""
    cached = cache_get("settings", "warehouse_defaults")
    if cached is not None:
        return cached
    
    defaults = {
        "default_warehouse": (
            frappe.db.get_single_value("Stock Settings", "default_warehouse")
            or "Finished Goods - AW"
        ),
        "default_wip_warehouse": (
            frappe.db.get_single_value("Manufacturing Settings", "default_wip_warehouse")
            or "Work In Progress - AW"
        ),
        "default_scrap_warehouse": (
            frappe.db.get_single_value("Manufacturing Settings", "default_scrap_warehouse")
            or "Scrap Warehouse - AW"
        ),
    }
    
    cache_set("settings", "warehouse_defaults", defaults)
    return defaults


# =============================================================================
# CUSTOMER METADATA CACHE
# =============================================================================

def get_customer_meta(customer: str) -> Optional[Dict]:
    """Get cached customer metadata for CFDI and payment terms."""
    cached = cache_get("customer_meta", customer)
    if cached is not None:
        return cached
    
    meta = frappe.db.get_value("Customer", customer,
        ["payment_terms", "mx_cfdi_use", "customer_name"],
        as_dict=True)
    
    if meta:
        cache_set("customer_meta", customer, meta)
        _track_key("customer_meta", customer)
    
    return meta


# =============================================================================
# BATCH STOCK CACHE (short TTL — stock changes frequently)
# =============================================================================

def get_available_batches(item_code: str, warehouse: str = None) -> List[Dict]:
    """Get available batches with stock, ordered FIFO by expiry.
    
    Uses short TTL (30s) since batch quantities change frequently.
    ERPNext v16: Queries Batch.batch_qty directly (Serial and Batch Bundle model).
    """
    cache_id = f"{item_code}:{warehouse or 'ALL'}"
    cached = cache_get("batch_stock", cache_id)
    if cached is not None:
        return cached
    
    batches = frappe.db.sql("""
        SELECT name as batch_no, batch_qty, expiry_date
        FROM `tabBatch`
        WHERE item = %s
          AND disabled = 0
          AND batch_qty > 0
          AND (expiry_date IS NULL OR expiry_date >= CURDATE())
        ORDER BY COALESCE(expiry_date, '9999-12-31') ASC
    """, (item_code,), as_dict=True)
    
    cache_set("batch_stock", cache_id, batches, ttl=CACHE_TTL["batch_stock"])
    return batches


def invalidate_batch_cache(item_code: str) -> None:
    """Invalidate batch stock cache for an item (call after stock transactions)."""
    # Delete both specific-warehouse and ALL entries
    cache_delete("batch_stock", f"{item_code}:ALL")
    # We can't enumerate all warehouses, so rely on short TTL


# =============================================================================
# TDS MAPPING CACHE
# =============================================================================

def get_tds_mapping_cached(sales_item: str, customer: str = None) -> Optional[Dict]:
    """Get cached TDS (Technical Data Sheet) mapping for a sales item."""
    cache_id = f"{sales_item}:{customer or 'ANY'}"
    cached = cache_get("tds_mapping", cache_id)
    if cached is not None:
        return cached if cached != "__NONE__" else None
    
    # This queries will be filled by the caller — we just provide the cache layer
    return None  # Caller should populate via set_tds_mapping_cache


def set_tds_mapping_cache(sales_item: str, customer: str, mapping: Dict) -> None:
    """Store TDS mapping in cache."""
    cache_id = f"{sales_item}:{customer or 'ANY'}"
    cache_set("tds_mapping", cache_id, mapping or "__NONE__")


# =============================================================================
# CACHE STATS (for monitoring/debugging)
# =============================================================================

def get_cache_stats() -> Dict:
    """Get cache usage stats for monitoring."""
    stats = {}
    for namespace in CACHE_TTL:
        tracker_key = f"{CACHE_PREFIX}_keys:{namespace}"
        known_keys = frappe.cache.get_value(tracker_key) or []
        hits = 0
        for key in known_keys:
            if frappe.cache.get_value(key) is not None:
                hits += 1
        stats[namespace] = {
            "tracked_keys": len(known_keys),
            "active_entries": hits,
            "ttl_seconds": CACHE_TTL[namespace]
        }
    return stats


@frappe.whitelist()
def api_cache_stats() -> str:
    """API endpoint to check cache stats."""
    return json.dumps(get_cache_stats(), indent=2)


@frappe.whitelist()
def api_clear_cache(namespace: str = None) -> str:
    """API endpoint to clear cache (specific namespace or all)."""
    if namespace and namespace in CACHE_TTL:
        cache_invalidate_namespace(namespace)
        return json.dumps({"status": "ok", "cleared": namespace})
    elif not namespace:
        for ns in CACHE_TTL:
            cache_invalidate_namespace(ns)
        return json.dumps({"status": "ok", "cleared": "all"})
    else:
        return json.dumps({"status": "error", "message": f"Unknown namespace: {namespace}"})
