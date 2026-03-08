"""
Performance Testing Suite for Raven AI Agent
Phase 2: Optimization

Measures latency for key operations before and after optimization.
Run via: bench --site [site] execute raven_ai_agent.api.perf_test.run_all_tests

Results are saved to Redis and can be retrieved via API.
"""
import frappe
import json
import time
from typing import Dict, List, Callable
from frappe.utils import now_datetime


# =============================================================================
# TEST RUNNER
# =============================================================================

class PerfTimer:
    """Context manager for timing operations."""
    def __init__(self, label: str):
        self.label = label
        self.start = None
        self.elapsed_ms = 0
    
    def __enter__(self):
        self.start = time.perf_counter()
        return self
    
    def __exit__(self, *args):
        self.elapsed_ms = (time.perf_counter() - self.start) * 1000


def run_test(name: str, fn: Callable, iterations: int = 5) -> Dict:
    """Run a test function multiple times and collect timing stats."""
    times = []
    errors = []
    
    for i in range(iterations):
        try:
            with PerfTimer(name) as t:
                fn()
            times.append(t.elapsed_ms)
        except Exception as e:
            errors.append(str(e))
    
    if not times:
        return {
            "name": name,
            "status": "ERROR",
            "errors": errors
        }
    
    return {
        "name": name,
        "status": "OK",
        "iterations": len(times),
        "min_ms": round(min(times), 2),
        "max_ms": round(max(times), 2),
        "avg_ms": round(sum(times) / len(times), 2),
        "p95_ms": round(sorted(times)[int(len(times) * 0.95)], 2) if len(times) >= 5 else round(max(times), 2),
        "errors": errors
    }


# =============================================================================
# TEST CASES
# =============================================================================

def test_item_meta_uncached():
    """Test: Fetch item metadata directly from DB (no cache)."""
    # Clear any existing cache
    try:
        from raven_ai_agent.api.cache_layer import cache_delete
        cache_delete("item_meta", "0803-")
    except ImportError:
        pass
    
    frappe.db.get_value("Item", "0803-",
        ["has_batch_no", "has_serial_no", "inspection_required_before_delivery",
         "stock_uom", "item_name"], as_dict=True)


def test_item_meta_cached():
    """Test: Fetch item metadata from Redis cache."""
    try:
        from raven_ai_agent.api.cache_layer import get_item_meta
        get_item_meta("0803-")  # First call populates cache, subsequent use it
    except ImportError:
        frappe.db.get_value("Item", "0803-",
            ["has_batch_no", "has_serial_no"], as_dict=True)


def test_batch_lookup_uncached():
    """Test: Query available batches directly from DB."""
    frappe.db.sql("""
        SELECT name as batch_no, batch_qty, expiry_date
        FROM `tabBatch`
        WHERE item = '0803-'
          AND disabled = 0
          AND batch_qty > 0
          AND (expiry_date IS NULL OR expiry_date >= CURDATE())
        ORDER BY COALESCE(expiry_date, '9999-12-31') ASC
    """, as_dict=True)


def test_batch_lookup_cached():
    """Test: Query available batches from Redis cache."""
    try:
        from raven_ai_agent.api.cache_layer import get_available_batches
        get_available_batches("0803-")
    except ImportError:
        test_batch_lookup_uncached()


def test_warehouse_defaults_uncached():
    """Test: Fetch warehouse defaults from DB (3 separate queries)."""
    frappe.db.get_single_value("Stock Settings", "default_warehouse")
    frappe.db.get_single_value("Manufacturing Settings", "default_wip_warehouse")
    frappe.db.get_single_value("Manufacturing Settings", "default_scrap_warehouse")


def test_warehouse_defaults_cached():
    """Test: Fetch warehouse defaults from single cached dict."""
    try:
        from raven_ai_agent.api.cache_layer import get_warehouse_defaults
        get_warehouse_defaults()
    except ImportError:
        test_warehouse_defaults_uncached()


def test_bom_lookup():
    """Test: Find default BOM for an item."""
    frappe.get_all("BOM",
        filters={"item": "0803-", "is_active": 1},
        fields=["name"],
        order_by="creation desc",
        limit=1)


def test_customer_meta():
    """Test: Fetch customer payment terms and CFDI fields."""
    customers = frappe.get_all("Customer", limit=1, fields=["name"])
    if customers:
        frappe.db.get_value("Customer", customers[0].name,
            ["payment_terms", "mx_cfdi_use", "customer_name"], as_dict=True)


def test_so_items_query():
    """Test: Fetch Sales Order with items (typical workflow start)."""
    sos = frappe.get_all("Sales Order",
        filters={"docstatus": 1},
        fields=["name"],
        limit=1)
    if sos:
        frappe.get_doc("Sales Order", sos[0].name)


def test_routing_detection():
    """Test: Intent detection latency."""
    try:
        from raven_ai_agent.api.handlers.router import _detect_ai_intent
        test_queries = [
            "create work order for 0307",
            "delivery from SO-00763",
            "pipeline status SO-00752",
            "unpaid invoices",
            "pending orders"
        ]
        for q in test_queries:
            _detect_ai_intent(q)
    except ImportError:
        pass  # Routing module not available


# =============================================================================
# MAIN TEST RUNNER
# =============================================================================

ALL_TESTS = [
    ("item_meta_uncached", test_item_meta_uncached, 10),
    ("item_meta_cached", test_item_meta_cached, 10),
    ("batch_lookup_uncached", test_batch_lookup_uncached, 10),
    ("batch_lookup_cached", test_batch_lookup_cached, 10),
    ("warehouse_defaults_uncached", test_warehouse_defaults_uncached, 10),
    ("warehouse_defaults_cached", test_warehouse_defaults_cached, 10),
    ("bom_lookup", test_bom_lookup, 5),
    ("customer_meta", test_customer_meta, 5),
    ("so_items_query", test_so_items_query, 3),
    ("routing_detection", test_routing_detection, 10),
]


def run_all_tests() -> Dict:
    """Run all performance tests and return results."""
    results = []
    total_start = time.perf_counter()
    
    for name, fn, iterations in ALL_TESTS:
        result = run_test(name, fn, iterations)
        results.append(result)
    
    total_ms = (time.perf_counter() - total_start) * 1000
    
    report = {
        "timestamp": str(now_datetime()),
        "total_ms": round(total_ms, 2),
        "tests": results,
        "summary": {
            "total": len(results),
            "passed": sum(1 for r in results if r["status"] == "OK"),
            "failed": sum(1 for r in results if r["status"] == "ERROR"),
        }
    }
    
    # Save to Redis for later comparison
    frappe.cache.set_value("rai:perf_results:latest", report, expires_in_sec=86400)
    
    # Also save with timestamp for historical comparison
    ts_key = now_datetime().strftime("%Y%m%d_%H%M%S")
    frappe.cache.set_value(f"rai:perf_results:{ts_key}", report, expires_in_sec=604800)
    
    return report


def print_results(report: Dict) -> str:
    """Format test results as a readable table."""
    lines = []
    lines.append(f"Performance Test Results — {report['timestamp']}")
    lines.append("=" * 70)
    lines.append(f"{'Test':<30} {'Avg (ms)':<12} {'Min':<10} {'Max':<10} {'P95':<10} {'Status'}")
    lines.append("-" * 70)
    
    for t in report["tests"]:
        if t["status"] == "OK":
            lines.append(
                f"{t['name']:<30} {t['avg_ms']:<12.2f} {t['min_ms']:<10.2f} "
                f"{t['max_ms']:<10.2f} {t['p95_ms']:<10.2f} OK"
            )
        else:
            lines.append(f"{t['name']:<30} {'—':<12} {'—':<10} {'—':<10} {'—':<10} ERROR")
    
    lines.append("-" * 70)
    s = report["summary"]
    lines.append(f"Total: {s['total']} tests, {s['passed']} passed, {s['failed']} failed")
    lines.append(f"Total time: {report['total_ms']:.0f} ms")
    
    return "\n".join(lines)


# =============================================================================
# API ENDPOINTS
# =============================================================================

@frappe.whitelist()
def api_run_perf_tests() -> str:
    """API: Run all performance tests and return results."""
    report = run_all_tests()
    return print_results(report)


@frappe.whitelist()
def api_get_perf_results() -> str:
    """API: Get latest performance test results."""
    report = frappe.cache.get_value("rai:perf_results:latest")
    if report:
        return print_results(report)
    return "No performance test results found. Run: @ai perf test"
