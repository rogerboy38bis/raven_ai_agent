# Deep Research: Raven AI Agent Pipeline Routing Issue

## Investigation Summary

The user reports that `@ai pipeline SAL-QTN-2024-00752` routes to `sales_order_bot` instead of `task_validator`.

## Research Findings

### 1. Code Analysis

**File:** `raven_ai_agent/api/handlers/router.py`

The intent detection happens in `_detect_ai_intent()` function. Current patterns:

- Line 37-40: SO-linked patterns → `sales_order_follow_up`
- Line 43-53: Orchestrator patterns → `workflow_orchestrator`  
- Line 56-70: Manufacturing patterns → `manufacturing_bot`
- Line 73-84: Payment patterns → `payment_bot`
- **Line 87-99: Validator patterns → `task_validator`** ← Target
- Line 102-113: Sales patterns → `sales_order_follow_up`
- Line 116: Default → `sales_order_bot`

### 2. Pattern Analysis for "pipeline SAL-QTN-2024-00752"

| Pattern | Match? |
|---------|--------|
| `SO-\d+` | ❌ No |
| `pipeline\s+status` | ❌ No |
| `validate\s+(?:pipeline\s+)?SAL-QTN` | ❌ No (no "validate") |
| `MFG-WO-\d+` | ❌ No |
| `ACC-PAY-*` | ❌ No |
| **`pipeline\s+SAL-QTN-`** | ✅ **YES** |

The validator pattern SHOULD match.

### 3. Possible Issues

#### Issue A: Server Not Restarted
The most likely cause - code pushed but server not restarted.

```bash
# On Frappe server:
cd /home/frappe/frappe-bench
bench get-app raven_ai_agent
bench --site [site] restart
```

#### Issue B: Python Cache
Old `.pyc` files may be serving stale code.

```bash
find /path/to/raven_ai_agent -name "*.pyc" -delete
find /path/to/raven_ai_agent -type d -name __pycache__ -exec rm -rf {} +
```

#### Issue C: Multiple Code Paths
There are multiple entry points:
- `handle_raven_message()` in router.py (for @ai commands via Raven)
- `process_message()` API endpoint (for direct API calls)

The user is using Raven chat interface, so router.py is correct.

### 4. Logs to Check

Enable debug logging:

```python
# In router.py _detect_ai_intent():
frappe.logger().info(f"[AI Intent] Query: {query}")
frappe.logger().info(f"[AI Intent] Validator patterns: {validator_patterns}")
for p in validator_patterns:
    m = re.search(p, query, re.IGNORECASE)
    if m:
        frappe.logger().info(f"[AI Intent] MATCHED: {p} -> {m.group()}")
        break
```

### 5. Quick Fix Verification

Test this directly in Frappe bench:

```bash
cd /home/frappe/frappe-bench
bench console
```

```python
import re
query = "pipeline SAL-QTN-2024-00752"
validator_patterns = [
    r'diagnos[ei]',
    r'validate\b',
    r'audit\s+pipeline',
    r'check\s+payment',
    r'check\s+pago',
    r'pipeline\s+health',
    r'verify\s+(?:SO|sales\s+order)',
    r'pipeline\s+SAL-QTN-',
    r'pipeline\s+QUOT-',
]
for p in validator_patterns:
    m = re.search(p, query, re.IGNORECASE)
    if m:
        print(f"MATCH: {p}")
        print(f"Matched text: {m.group()}")
        break
```

---

## Action Items

1. **User:** Pull latest code and restart Frappe server
2. **User:** Check logs: `tail -f logs/frappe.log | grep "AI Agent"`
3. **If still failing:** Add debug logging to trace exact pattern matching

---

## Files Modified in Fix

| File | Change |
|------|--------|
| `raven_ai_agent/api/handlers/router.py` | Added `r'pipeline\s+SAL-QTN-'` to validator_patterns |
| `raven_ai_agent/api/handlers/task_validator.py` | Added handler for pipeline command |
| `docs/deep_routing_analysis_report.md` | This report |

---

**Research by:** MiniMax Agent  
**Date:** 2026-03-13
