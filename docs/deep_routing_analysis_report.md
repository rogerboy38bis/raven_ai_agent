# Deep Analysis Report: Pipeline Command Routing Issue

**Date:** 2026-03-13  
**Issue:** `@ai pipeline SAL-QTN-XXXX` incorrectly routes to `sales_order_bot` instead of `task_validator`  
**Priority:** High  
**Status:** Under Investigation

---

## Executive Summary

The command `@ai pipeline SAL-QTN-2024-00752` is being routed to `sales_order_bot` when it should be routed to `task_validator`. This report documents the deep investigation into the routing mechanism.

---

## Current Architecture

### Message Flow

```
User Message (@ai pipeline SAL-QTN-2024-00752)
        ↓
handle_raven_message() [router.py line 119]
        ↓
Extract query: "pipeline SAL-QTN-2024-00752"
        ↓
_detect_ai_intent(query) [line 26]
        ↓
Pattern Matching (lines 33-116)
        ↓
Return bot_name → Execute handler
```

### Intent Detection Logic (_detect_ai_intent)

The function checks patterns in this order:

| # | Pattern Group | Patterns | Returns |
|---|--------------|----------|---------|
| 1 | SO-linked | `SO-\d+`, `from\s+SO` | `sales_order_follow_up` |
| 2 | Orchestrator | `pipeline\s+status`, `validate\s+pipeline`, etc. | `workflow_orchestrator` |
| 3 | Manufacturing | `MFG-WO-\d+`, `work order`, etc. | `manufacturing_bot` |
| 4 | Payment | `ACC-PAY-*`, `payment`, etc. | `payment_bot` |
| 5 | **Validator** | `diagnos[ei]`, `pipeline\s+SAL-QTN-`, etc. | **`task_validator`** |
| 6 | Sales | `pending orders`, `create invoice`, etc. | `sales_order_follow_up` |
| 7 | **Default** | None matched | `sales_order_bot` |

---

## Root Cause Analysis

### Code Analysis (Local - Commit 83d3f34)

The router.py file at lines 87-99 contains:

```python
# Task Validator / Diagnosis
validator_patterns = [
    r'diagnos[ei]',
    r'validate\b',
    r'audit\s+pipeline',
    r'check\s+payment',
    r'check\s+pago',
    r'pipeline\s+health',
    r'verify\s+(?:SO|sales\s+order)',
    r'pipeline\s+SAL-QTN-',   # ← Added in commit 83d3f34
    r'pipeline\s+QUOT-',       # ← Added in commit 83d3f34
]
if any(re.search(p, query, re.IGNORECASE) for p in validator_patterns):
    return "task_validator"
```

### Regex Testing (Verified)

```
Query: "pipeline SAL-QTN-2024-00752"

Test: r'pipeline\s+SAL-QTN-'
Result: ✓ MATCHES "pipeline SAL-QTN-"

Expected: Return "task_validator"
Actual (production): Returns "sales_order_bot"
```

---

## Possible Causes

### 1. Server Not Restarted (Most Likely)

The Frappe/ERPNext application needs to be restarted to pick up code changes. The router.py changes are in the git repository but may not be loaded in the running application.

**Verification:** Check if `bench --site [site] restart` has been run after git pull.

### 2. Cached Python Files

Python's `.pyc` cache files may be serving old code.

**Solution:** 
```bash
cd /workspace/raven_ai_agent
find . -type d -name __pycache__ -exec rm -rf {} +
find . -name "*.pyc" -delete
```

### 3. Multiple Router Implementations

There are multiple router files in the project:

```
raven_ai_agent/raven_ai_agent/api/router.py
raven_ai_agent/raven_ai_agent/api/handlers/router.py  ← This is the active one
raven_ai_agent/raven_ai_agent/skills/router.py
raven_ai_agent/raven_ai_agent/gateway/router.py
```

The active handler is `api/handlers/router.py`.

### 4. Git Push Not Reaching Server

Verify the commit is on the remote:
```bash
git log --oneline origin/main -5
```

Expected output:
```
83d3f34 fix: Route pipeline SAL-QTN commands to task_validator
c5c3093 fix: Force pipeline diagnosis for SAL-QTN in diagnose/pipeline commands
```

---

## Handler Code (task_validator.py)

Even when routed correctly, the handler needs to process the command. Added in commit 83d3f34:

```python
# PIPELINE: Quick pipeline diagnosis (shorthand for diagnose)
# @ai pipeline SAL-QTN-XXXX
if "pipeline" in query_lower and "audit" not in query_lower:
    qtn_match = re.search(r'(SAL-QTN-\d+-\d+)', query, re.IGNORECASE)
    if qtn_match:
        return self._diagnose_from_quotation(qtn_match.group(1).upper())
    else:
        return {
            "success": False,
            "error": "**Usage:** `@ai pipeline SAL-QTN-2024-XXXXX`"
        }
```

---

## Recommendations

1. **Immediate:** Restart the Frappe bench after pulling latest code:
   ```bash
   cd /home/frappe/frappe-bench
   bench get-app raven_ai_agent
   bench --site [site] restart
   ```

2. **Verify:** Check logs for intent detection:
   ```bash
   tail -f logs/frappe.log | grep "AI Agent.*intent"
   ```

3. **Debug:** Add more logging to _detect_ai_intent to see actual pattern matching

---

## Test Commands

After fix deployment, these should all route to task_validator:

| Command | Expected Bot |
|---------|-------------|
| `@ai diagnose SAL-QTN-2024-00752` | task_validator ✅ |
| `@ai scan SAL-QTN-2024-00752` | task_validator ✅ |
| `@ai pipeline SAL-QTN-2024-00752` | task_validator ✅ |
| `@ai audit pipeline SAL-QTN-2024-00752` | task_validator ✅ |

---

**Investigated by:** MiniMax Agent  
**For:** Raven AI Agent Development Team
