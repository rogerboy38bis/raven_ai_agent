# Raven AI Agent: Pipeline Command Routing Issue Report

**Document Type:** Technical Investigation Report  
**Date:** March 13, 2026  
**Issue:** `@ai pipeline SAL-QTN-XXXX` Incorrect Routing  
**Status:** Fix Deployed - Awaiting Server Restart

---

## 1. Executive Summary

This report documents the investigation and resolution of a routing issue in the Raven AI Agent system. The command `@ai pipeline SAL-QTN-2024-00752` was incorrectly routed to the `sales_order_bot` handler instead of the `task_validator` handler, preventing users from accessing quotation pipeline diagnostics.

**Root Cause:** Pattern matching logic in the intent detection system did not include a specific pattern for pipeline commands targeting quotations.

**Resolution:** Added new routing patterns and handler logic to properly route pipeline commands to the task validator.

---

## 2. Problem Statement

### 2.1 Observed Behavior

| Command | Expected Handler | Actual Handler |
|---------|-----------------|----------------|
| `@ai diagnose SAL-QTN-2024-00752` | task_validator ✅ | task_validator ✅ |
| `@ai scan SAL-QTN-2024-00752` | task_validator ✅ | task_validator ✅ |
| `@ai pipeline SAL-QTN-2024-00752` | task_validator ❌ | sales_order_bot ❌ |

### 2.2 User Impact

- Users could not access the full pipeline diagnosis for quotations using the `pipeline` keyword
- Had to use `diagnose` as a workaround
- Inconsistent user experience across similar commands

---

## 3. Technical Analysis

### 3.1 Architecture Overview

The Raven AI Agent uses a multi-stage routing system:

```
User Message → handle_raven_message() → _detect_ai_intent() → Execute Handler
```

The `_detect_ai_intent()` function in `router.py` uses regex pattern matching to determine which specialized agent should handle each command.

### 3.2 Pattern Matching Order

The intent detection checks patterns in a specific priority order:

1. **SO-linked commands** → `sales_order_follow_up`
2. **Orchestrator commands** → `workflow_orchestrator`
3. **Manufacturing commands** → `manufacturing_bot`
4. **Payment commands** → `payment_bot`
5. **Validator commands** → `task_validator`
6. **Sales commands** → `sales_order_follow_up`
7. **Default fallback** → `sales_order_bot`

### 3.3 Root Cause

The query `pipeline SAL-QTN-2024-00752` did not match any of the existing validator patterns:

- `pipeline\s+status` - Requires "status" keyword
- `pipeline\s+health` - Requires "health" keyword  
- `audit\s+pipeline` - Requires "audit" keyword

Since no pattern matched, the query fell through to the default handler (`sales_order_bot`).

---

## 4. Solution Implemented

### 4.1 Router.py Changes

Added new patterns to the validator pattern list in `api/handlers/router.py`:

```python
validator_patterns = [
    r'diagnos[ei]',
    r'validate\b',
    r'audit\s+pipeline',
    r'check\s+payment',
    r'check\s+pago',
    r'pipeline\s+health',
    r'verify\s+(?:SO|sales\s+order)',
    r'pipeline\s+SAL-QTN-',    # NEW: Pipeline for quotations
    r'pipeline\s+QUOT-',        # NEW: Alternative prefix
]
```

### 4.2 Task Validator Handler Changes

Added handler logic in `api/handlers/task_validator.py`:

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

## 5. Testing

### 5.1 Local Regex Verification

Tested pattern matching locally:

```
Query: "pipeline SAL-QTN-2024-00752"

Pattern: r'pipeline\s+SAL-QTN-'
Result: ✓ MATCHES "pipeline SAL-QTN-"

Expected Route: task_validator
```

### 5.2 Expected Results After Deployment

| Command | Expected Handler | Expected Output |
|---------|-----------------|-----------------|
| `@ai diagnose SAL-QTN-2024-00752` | task_validator | Full pipeline diagnosis |
| `@ai scan SAL-QTN-2024-00752` | task_validator | Basic scan summary |
| `@ai pipeline SAL-QTN-2024-00752` | task_validator | Full pipeline diagnosis |
| `@ai audit pipeline SAL-QTN-2024-00752` | task_validator | Deep audit report |

---

## 6. Deployment Steps

### 6.1 On Frappe Server

```bash
# 1. Navigate to app directory
cd /home/frappe/frappe-bench/apps/raven_ai_agent

# 2. Pull latest changes
git pull origin main

# 3. Clear Python cache
find . -name "*.pyc" -delete
find . -type d -name __pycache__ -exec rm -rf {} +

# 4. Restart bench
bench --site [your-site-name] restart

# 5. Verify logs
tail -f logs/frappe.log | grep "AI Agent"
```

### 6.2 Verification Commands

After restart, test with:
```
@ai pipeline SAL-QTN-2024-00752
```

---

## 7. Files Modified

| File | Change Type | Description |
|------|------------|-------------|
| `api/handlers/router.py` | Modified | Added pipeline SAL-QTN patterns |
| `api/handlers/task_validator.py` | Modified | Added pipeline command handler |
| `docs/deep_routing_analysis_report.md` | New | Technical analysis document |
| `docs/pipeline_routing_research.md` | New | Research findings |

### Commit Information

- **Commit Hash:** `83d3f34`
- **Message:** "fix: Route pipeline SAL-QTN commands to task_validator"

---

## 8. Recommendations

### 8.1 Immediate Actions

1. Server restart is required to activate the fix
2. Monitor logs after restart to confirm correct routing
3. Test all pipeline-related commands

### 8.2 Future Improvements

1. Add debug logging to track pattern matching in production
2. Consider a unified command syntax for all document types
3. Document all available commands in user-facing documentation

---

## 9. Conclusion

The issue has been identified and resolved in the codebase. The fix adds proper pattern matching for pipeline commands targeting quotations, ensuring consistent routing to the task validator handler. The solution is ready for deployment pending server restart.

---

**Report Prepared By:** MiniMax Agent  
**Date:** March 13, 2026  
**For:** Raven AI Agent Development Team
