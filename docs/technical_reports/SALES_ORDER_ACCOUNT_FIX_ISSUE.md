# Technical Report: Sales Order Account Fix Issue

## Executive Summary

The Data Quality Scanner identifies "Group Account" issues in Sales Orders, but attempting to fix them fails because Sales Orders don't have a `debit_to` field. This report analyzes the issue and proposes potential solutions.

---

## Problem Description

### Current Behavior

1. **Scanner detects issue**: The scanner calls `erpnext.accounts.party.get_party_account()` which returns a **group account** (e.g., "1105 - CLIENTES - AMB-W")

2. **Issue flagged as CRITICAL**:
   ```
   Account '1105 - CLIENTES - AMB-W' is a Group Account (cannot be used in transactions)
   Field: debit_to
   Fix: find_leaf_account (80% confidence)
   ```

3. **Fix attempt fails**:
   ```
   Could not save: (1054, "Unknown column 'debit_to' in 'SET'")
   ```

### Root Cause

- **Sales Orders** do NOT have a `debit_to` field
- The `debit_to` field only exists on **Sales Invoices**
- Accounts are assigned dynamically at **invoice creation time**, not when the order is created

---

## Technical Analysis

### How ERPNext Handles Receivable Accounts

| Document Type | Has debit_to? | When Account is Set |
|---------------|---------------|---------------------|
| Sales Order | ❌ No | N/A - not applicable |
| Sales Invoice | ✅ Yes | At invoice creation |
| Quotation | ❌ No | N/A - not applicable |

### Account Resolution Flow

```
Sales Order → Create Sales Invoice → get_party_account() → Sets debit_to
```

The function `get_party_account("Customer", customer, company)` is called at **invoice creation time**, not order time.

---

## Current Workaround (Skipping)

We've implemented a temporary fix that **skips** the account fix for Sales Orders:

```python
if doc_type == "Sales Order":
    skipped.append("Skipped debit_to fix - accounts are set at Invoice level")
    continue
```

**Pros:**
- ✅ Fixes applied successfully (Cost Center, Address)
- ✅ No errors

**Cons:**
- ❌ Group Account issue remains flagged
- ❌ Not a real solution - just hiding the problem

---

## Potential Solutions

### Option 1: Fix at Invoice Level (RECOMMENDED)

**Description**: Run the scanner on Sales Invoices instead of Orders, or create a separate "Invoice Ready" check.

**Pros:**
- ✅ Actually solves the problem
- ✅ Debit_to field exists on invoices

**Cons:**
- ❌ User needs to run scan AFTER creating invoice
- ❌ Two-step process

### Option 2: Set Default Account on Customer

**Description**: Update the default receivable account on the **Customer** record.

```python
# Set default receivable on customer
customer = frappe.get_doc("Customer", customer_name)
customer.default_receivable_account = "1310 - Debtors - AMB-W"
customer.save()
```

**Pros:**
- ✅ Fixes the root cause
- ✅ Future orders/invoices will use correct account

**Cons:**
- ❌ May affect all transactions for that customer
- ❌ Requires write access to Customer master

### Option 3: Override Party Account via Custom Field

**Description**: Add a custom field on Sales Order to override the account, then use a custom script to apply it at invoice time.

**Pros:**
- ✅ User can specify desired account

**Cons:**
- ❌ Complex to implement
- ❌ Requires custom app

### Option 4: Use Hook to Auto-Replace at Invoice Creation

**Description**: Create a custom app with a hook that replaces group accounts with leaf accounts at invoice creation.

```python
# In custom app hooks.py
doc_events.on("Sales Invoice", "before_save", "fix_group_accounts")
```

**Pros:**
- ✅ Automatic solution
- ✅ Works for all invoices

**Cons:**
- ❌ Requires custom app development
- ❌ More complex

---

## Questions for Development Team

1. **Is there a standard ERPNext way** to set a default receivable account per Customer that ensures it's always a leaf account?

2. **Should we modify the scanner** to detect document type and skip account validation for Sales Orders entirely (since it's not applicable)?

3. **Is there a custom field** on Sales Orders in our system that could store the receivable account override?

4. **Would a custom app** that automatically replaces group accounts at invoice creation be worth the development effort?

5. **What's the business requirement** - do we need to fix accounts at Order level, or is it acceptable to fix at Invoice level?

---

## Recommendation

**Short Term**: Keep the "skip" workaround (already implemented) - it allows other fixes (Cost Center, Address) to work.

**Medium Term**: Run separate scans on Sales Invoices to catch account issues at the right time.

**Long Term**: Consider a custom app or customer-level default account setting to ensure leaf accounts are always used.

---

## Contact

For questions about this issue, contact the Raven AI Agent development team.

---
*Generated: 2026-03-13*
