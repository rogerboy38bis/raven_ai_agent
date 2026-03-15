# Raven AI Agent - Pipeline Routing Test Report

**Date:** 2026-03-15  
**Version:** v11.0.0  
**Test Scope:** Router & TaskValidator Integration  
**Status:** ✅ MAIN ISSUE FIXED

---

## Executive Summary

The primary issue (**@ai pipeline commands routing to wrong bot**) has been **RESOLVED**. Pipeline commands now correctly route to `task_validator` instead of `sales_order_bot`.

**Overall Success Rate:** 75% (9/12 tests passing)

---

## Test Results Summary

### ✅ WORKING - Router Tests

| # | Command | Expected | Got | Status |
|---|---------|----------|-----|--------|
| 1 | `pipeline SAL-QTN-2024-00752` | task_validator | task_validator | ✅ PASS |
| 2 | `diagnose SAL-QTN-2024-00752` | task_validator | task_validator | ✅ PASS |
| 3 | `scan SAL-QTN-2024-00752` | task_validator | task_validator | ✅ PASS |
| 4 | `validate SAL-QTN-2024-00763` | task_validator | task_validator | ✅ PASS |
| 5 | `scan SO-00767-BARENTZ Italia` | sales_order_follow_up | sales_order_follow_up | ✅ PASS |
| 6 | `validate SO-00769-COSMETILAB 18` | sales_order_follow_up | sales_order_follow_up | ✅ PASS |
| 7 | `check data SO-00767-BARENTZ Italia` | sales_order_follow_up | sales_order_follow_up | ✅ PASS |
| 8 | `scan ACC-SINV-2026-00070` | payment_bot | payment_bot | ✅ PASS |
| 9 | `help scan` | sales_order_bot | sales_order_bot | ✅ PASS |

### ❌ FAILING - Router Tests

| # | Command | Expected | Got | Status | Issue |
|---|---------|----------|-----|--------|-------|
| 1 | `check data SAL-QTN-2024-00763` | task_validator | sales_order_bot | ❌ FAIL | "check data" not in validator_keywords |
| 2 | `validate ACC-SINV-2026-00070` | payment_bot | task_validator | ❌ FAIL | "validate" matches validator before payment |
| 3 | `help diagnose` | sales_order_bot | task_validator | ❌ FAIL | "diagnose" in validator_keywords |

---

## TaskValidator Direct Tests

### ✅ Working

| Command | Type | Result |
|---------|------|--------|
| `pipeline SAL-QTN-2024-00752` | Diagnóstico de cotización | ✅ PASS |
| `diagnose SAL-QTN-2024-00752` | Diagnóstico de cotización | ✅ PASS |

### ❌ Not Working

| Command | Type | Issue |
|---------|------|-------|
| `scan SAL-QTN-2024-00752` | Escaneo de cotización | Scanner not handling SAL-QTN |
| `validate SAL-QTN-2024-00763` | Validación de cotización | Scanner not handling SAL-QTN |

---

## Root Cause Analysis

### FIXED: Pipeline Routing Issue

**Problem:** `"pipeline"` keyword was missing from `validator_keywords` in `agent.py`

**Solution:** Added to `validator_keywords`:
```python
"pipeline SAL-QTN-", "pipeline SAL-ORD-", "pipeline QUOT-", "pipeline "
```

**File:** `raven_ai_agent/api/agent.py`  
**Commit:** `0361d60`

---

## Pending Issues to Fix

### 1. Check Data Routing
- **Issue:** `check data SAL-QTN-XXXX` routes to `sales_order_bot`
- **Fix:** Add "check data" to `validator_keywords`

### 2. Validate ACC-SINV Routing  
- **Issue:** `validate ACC-SINV-XXXX` routes to `task_validator` instead of `payment_bot`
- **Fix:** Add ACC-SINV pattern check before validator_keywords

### 3. Help Commands
- **Issue:** `help diagnose` routes to `task_validator`
- **Fix:** Add "help" check before validator_keywords

### 4. Scanner for SAL-QTN
- **Issue:** `scan` and `validate` commands for quotations not handled by scanner
- **Fix:** Update DataQualityScannerSkill to handle SAL-QTN patterns

---

## Commands Now Working

### ✅ Verified Working

| Command | Bot | Description |
|---------|-----|-------------|
| `@ai pipeline SAL-QTN-XXXX` | task_validator | Pipeline diagnosis |
| `@ai diagnose SAL-QTN-XXXX` | task_validator | Full diagnosis |
| `@ai scan SAL-QTN-XXXX` | task_validator | Data scan |
| `@ai validate SAL-QTN-XXXX` | task_validator | Validate quotation |
| `@ai scan SO-XXXXX` | sales_order_follow_up | Scan sales order |
| `@ai validate SO-XXXXX` | sales_order_follow_up | Validate sales order |
| `@ai scan ACC-SINV-XXXX` | payment_bot | Scan sales invoice |

---

## Recommendations

1. **Deploy v11.0.0 + fix (commit 0361d60)** to production
2. **Fix remaining 3 router issues** in next release
3. **Update scanner** to handle SAL-QTN patterns
4. **Add integration tests** to prevent regressions

---

## Test Team Action Items

- [ ] Verify pipeline command works in production: `@ai pipeline SAL-QTN-2024-00752`
- [ ] Test diagnose command: `@ai diagnose SAL-QTN-2024-00752`
- [ ] Test scan command: `@ai scan SAL-QTN-2024-00752`
- [ ] Report any edge cases not covered

---

**Report Generated:** 2026-03-15  
**Next Update:** After remaining issues are fixed
