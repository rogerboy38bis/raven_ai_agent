# Issue Report: Pipeline Command Routing for Quotations

**Date:** 2026-03-13  
**Priority:** High  
**Status:** Needs Development Team Assistance

---

## Summary

The command `@ai pipeline SAL-QTN-2024-00752` is being incorrectly routed to `sales_order_bot` instead of `task_validator` (which handles the data quality scanner for quotations).

## Observed Behavior

| Command | Expected Routing | Actual Routing |
|---------|-----------------|----------------|
| `@ai diagnose SAL-QTN-2024-00752` | task_validator ✅ | task_validator ✅ |
| `@ai scan SAL-QTN-2024-00752` | task_validator ✅ | task_validator ✅ |
| `@ai pipeline SAL-QTN-2024-00752` | task_validator ❌ | sales_order_bot ❌ |

## Root Cause Analysis

**File:** `raven_ai_agent/api/handlers/router.py`  
**Function:** `_detect_ai_intent()`

The intent detection function uses pattern matching to route commands to the appropriate agent. The current patterns in lines 43-53 (orchestrator patterns) and 87-97 (validator patterns) do not include a specific pattern for `pipeline SAL-QTN-XXXXX`.

### Current Patterns:

```python
# Orchestrator patterns (line 43-51)
orch_patterns = [
    r'pipeline\s+status',           # ✅ Matches "pipeline status"
    r'(?:run|start)\s+full\s+cycle',
    r'dry\s+run',
    r'validate\s+SO-',
    r'validate\s+(?:pipeline\s+)?SAL-QTN',  # ❌ Doesn't match "pipeline SAL-QTN"
    r'validate\s+pipeline',
    r'run\s+pipeline',
]

# Validator patterns (line 87-95)
validator_patterns = [
    r'diagnos[ei]',                 # ✅ Matches "diagnose"
    r'validate\b',
    r'audit\s+pipeline',
    r'check\s+payment',
    r'pipeline\s+health',
    # ❌ Missing: r'pipeline\s+SAL-QTN-'
]

# Default fallback (line 113-114)
return "sales_order_bot"           # ← This is why pipeline SAL-QTN goes here!
```

### Why It Fails:

1. `@ai pipeline SAL-QTN-2024-00752` does NOT match `pipeline\s+status` (no "status")
2. It does NOT match any validator pattern
3. It falls through to the default: `sales_order_bot`

## Proposed Fix

Add a new pattern to `validator_patterns` in `router.py`:

```python
validator_patterns = [
    r'diagnos[ei]',
    r'validate\b',
    r'audit\s+pipeline',
    r'check\s+payment',
    r'check\s+pago',
    r'pipeline\s+health',
    r'verify\s+(?:SO|sales\s+order)',
    # ADD THIS LINE:
    r'pipeline\s+SAL-QTN-',         # Matches "pipeline SAL-QTN-XXXXX"
]
```

## Questions for Development Team

1. Is this the correct approach, or should we create a separate pattern group?
2. Should we also support other document types in the pipeline command (e.g., `pipeline SO-XXXXX`)?
3. Are there any other similar commands that might be affected?

## Impact

- **User Experience:** Users cannot get full pipeline diagnosis for quotations using the `pipeline` command
- **Workaround:** Users must use `diagnose` instead of `pipeline` for quotations

---

**Reported by:** MiniMax Agent  
**For:** Raven AI Agent Development Team
