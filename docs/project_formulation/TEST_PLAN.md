# 8-Step Workflow — Comprehensive Test Plan
## raven_ai_agent / Manufacturing-to-Payment Pipeline

**Version:** 1.0
**Date:** 2026-03-03
**Author:** raven_ai_agent orchestrator
**Repo:** github.com/rogerboy38/raven_ai_agent (branch: main)

---

## Test Environment

| Field | Value |
|-------|-------|
| Site | erp.sysmayal2.cloud |
| Company | AMB-Wellness |
| Currency (Company) | MXN |
| Currency (Sales) | USD |
| Pilot SO | SO-00752-LEGOSAN AB |
| Pilot Item (Sales) | 0307 — INNOVALOE ALOE VERA GEL SPRAY DRIED POWDER 200:1 |
| Pilot Item (Mix) | ITEM_0612185231 — ALOE 70% + GOMA BB 30% |
| Sales BOM | BOM-0307-001 (0307 + LBL0307) |
| Mix BOM | BOM-0307-005 (ITEM_0612185231 + LBL4INX6INBL) |
| Test Qty | 150 Kg |

---

## Phase 1: Unit Tests — Manufacturing Agent

### MFG-001: Create Work Order
**Input:** `@manufacturing create wo for 0307 qty 150 bom BOM-0307-005`
**Expected:**
- WO created with status: Draft
- production_item = 0307
- bom_no = BOM-0307-005
- qty = 150
- Response includes WO link

### MFG-002: Create WO — Default BOM
**Input:** `@manufacturing create wo for 0307 qty 150`
**Expected:**
- Uses BOM-0307-001 (is_default=1)
- WO created successfully

### MFG-003: Create WO — Invalid Item
**Input:** `@manufacturing create wo for NONEXISTENT qty 100`
**Expected:**
- Returns error: "Item 'NONEXISTENT' not found"
- No WO created

### MFG-004: Create WO — No BOM
**Input:** `@manufacturing create wo for LBL4INX6INBL qty 100`
(assuming LBL4INX6INBL has no BOM)
**Expected:**
- Returns error: "No active BOM found"

### MFG-005: Submit Work Order
**Input:** `@manufacturing submit wo MFG-WO-XXXXX`
**Expected:**
- WO docstatus changes from 0 → 1
- Status shows "Not Started" or similar
- Response includes next step hint

### MFG-006: Submit Already-Submitted WO
**Input:** `@manufacturing submit wo MFG-WO-XXXXX` (already submitted)
**Expected:**
- Returns "already submitted" message
- No error thrown

### MFG-007: Material Transfer
**Input:** `@manufacturing transfer materials MFG-WO-XXXXX`
**Expected:**
- Stock Entry created with type "Material Transfer for Manufacture"
- Items transferred from source warehouse to WIP
- Response includes SE link

### MFG-008: Stock Entry Manufacture
**Input:** `@manufacturing manufacture MFG-WO-XXXXX`
**Expected:**
- Stock Entry created with type "Manufacture"
- Raw materials consumed from WIP
- FG produced into fg_warehouse
- Response includes SE link and qty manufactured

### MFG-009: Partial Manufacture
**Input:** `@manufacturing manufacture MFG-WO-XXXXX qty 75`
**Expected:**
- Only 75 Kg manufactured (out of 150 total)
- WO still In Process (not Completed)

### MFG-010: Create WO from Sales Order
**Input:** `@manufacturing create wo from so SO-00752-LEGOSAN AB`
**Expected:**
- WO created for item 0307 with qty 150
- WO.sales_order = SO-00752-LEGOSAN AB
- Uses default sales BOM

### MFG-011: WO Status Check
**Input:** `@manufacturing status MFG-WO-XXXXX`
**Expected:**
- Shows production_item, qty, produced_qty
- Lists linked Stock Entries
- Shows next action based on status

### MFG-012: Material Availability Check
**Input:** `@manufacturing check materials MFG-WO-XXXXX`
**Expected:**
- Table with item_code, required_qty, available_qty, status
- Reports whether all materials are available

---

## Phase 2: Unit Tests — Sales Order Follow-up Agent (Updated)

### SO-001: Create SO from Quotation
**Input:** `@sales_order_follow_up create from quotation SAL-QTN-2024-00752`
**Expected:**
- Sales Order created, linked to Quotation
- Quotation status changes to "Ordered"
- Response includes SO link

### SO-002: Submit Sales Order
**Input:** `@sales_order_follow_up submit SO-00752-LEGOSAN AB`
**Expected:**
- SO docstatus 0 → 1
- Response includes next step hints (manufacturing WO)

### SO-003: Submit Already-Submitted SO
**Input:** `@sales_order_follow_up submit SO-00752-LEGOSAN AB` (already submitted)
**Expected:**
- Returns "already submitted" with status info
- No error

### SO-004: Create Delivery Note — Sufficient Stock
**Pre-condition:** 150 Kg of 0307 in FG to Sell Warehouse
**Input:** `@sales_order_follow_up delivery SO-00752-LEGOSAN AB`
**Expected:**
- DN created and submitted
- Items pulled from FG to Sell
- Response includes DN link

### SO-005: Create Delivery Note — Insufficient Stock
**Pre-condition:** 0 Kg of 0307 in warehouse
**Input:** `@sales_order_follow_up delivery SO-00752-LEGOSAN AB`
**Expected:**
- Returns error with shortage details
- Suggests creating Manufacturing WO
- No DN created

### SO-006: Create Sales Invoice from DN
**Pre-condition:** DN exists for SO-00752
**Input:** `@sales_order_follow_up invoice SO-00752-LEGOSAN AB`
**Expected:**
- SI created from latest Delivery Note
- mx_cfdi_use = "G03"
- custom_customer_invoice_currency = USD
- SI submitted

### SO-007: Create Sales Invoice — No DN
**Pre-condition:** No DN exists, from_dn=False
**Input:** `@sales_order_follow_up invoice SO-00752-LEGOSAN AB` (with `from so` modifier)
**Expected:**
- SI created directly from SO
- CFDI fields set correctly

### SO-008: SO Status with Work Orders
**Input:** `@sales_order_follow_up status SO-00752-LEGOSAN AB`
**Expected:**
- Shows linked Work Orders with status and progress
- Shows linked DNs, SIs
- Shows next recommended action

### SO-009: Pending Orders List
**Input:** `@sales_order_follow_up pending`
**Expected:**
- Table of all pending SOs
- Each with customer, status, delivery date, next action

### SO-010: Next Steps — Manufacturing Aware
**Input:** `@sales_order_follow_up next SO-00752-LEGOSAN AB`
**Expected:**
- If no stock: suggests `@manufacturing create wo from so`
- If WO in progress: shows WO status
- If stock available: suggests DN creation

---

## Phase 3: Unit Tests — Payment Agent

### PAY-001: Create Payment Entry
**Input:** `@payment create ACC-SINV-2026-00001`
**Expected:**
- PE created referencing the SI
- Amount = outstanding_amount
- Status: Draft
- Response includes PE link

### PAY-002: Partial Payment
**Input:** `@payment create ACC-SINV-2026-00001 amount 5000`
**Expected:**
- PE created with paid_amount = 5000
- SI still has remaining outstanding

### PAY-003: Submit Payment Entry
**Input:** `@payment submit ACC-PAY-2026-00001`
**Expected:**
- PE docstatus 0 → 1
- SI outstanding_amount decreases

### PAY-004: Payment Already Paid
**Input:** `@payment create ACC-SINV-2026-00001` (outstanding = 0)
**Expected:**
- Returns "already fully paid" message
- No PE created

### PAY-005: Reconciliation Check
**Input:** `@payment reconcile ACC-PAY-2026-00001`
**Expected:**
- Shows allocated amounts per invoice
- Reports whether fully reconciled

### PAY-006: Outstanding Invoices
**Input:** `@payment outstanding`
**Expected:**
- List of all unpaid Sales Invoices
- Total outstanding amount

### PAY-007: Outstanding by Customer
**Input:** `@payment outstanding customer LEGOSAN AB`
**Expected:**
- Filtered list for LEGOSAN AB only

---

## Phase 4: Unit Tests — Workflow Orchestrator

### WF-001: Pipeline Status Dashboard
**Input:** `@workflow status SO-00752-LEGOSAN AB`
**Expected:**
- 8-step dashboard table
- Each step shows: status, document link, complete/pending
- Progress percentage
- Next action highlighted

### WF-002: Create SO from Quotation
**Input:** `@workflow create so from SAL-QTN-2024-00752`
**Expected:**
- SO created and linked
- Same as SO-001

### WF-003: Run Full Cycle
**Input:** `@workflow run SO-00752-LEGOSAN AB mfg-bom BOM-0307-005 sales-bom BOM-0307-001`
**Expected:**
- All 8 steps execute in sequence
- Each step reports success/failure
- Final summary shows completed count

### WF-004: Run with Skip Steps
**Input:** `@workflow run SO-00752-LEGOSAN AB skip [1,2,3]`
**Pre-condition:** Steps 1-3 already done (MFG WO completed, SO submitted)
**Expected:**
- Steps 1-3 marked as "Skipped"
- Steps 4-8 execute normally

### WF-005: Full Cycle — Error Handling
**Pre-condition:** SO not submitted, insufficient stock
**Input:** `@workflow run SO-00752-LEGOSAN AB`
**Expected:**
- Pipeline stops at first failing step
- Shows which steps completed vs failed
- Provides actionable error message

---

## Phase 5: Integration Tests — Full Pipeline

### INT-001: Complete Folio 0752 Workflow
**Pre-conditions:**
- SO-00752-LEGOSAN AB exists (Draft)
- BOM-0307-005 submitted (ITEM_0612185231 + LBL4INX6INBL)
- BOM-0307-001 submitted (0307 + LBL0307)
- 150 Kg ITEM_0612185231 in FG to Sell
- 100 LBL4INX6INBL in FG to Sell
- 100 LBL0307 in FG to Sell

**Steps:**
```
Step 1: @manufacturing create wo for 0307 qty 150 bom BOM-0307-005
        → Verify: MFG-WO created, Draft
Step 2: @manufacturing submit wo MFG-WO-XXXXX
        @manufacturing transfer materials MFG-WO-XXXXX
        @manufacturing manufacture MFG-WO-XXXXX
        → Verify: 150 Kg 0307 now in FG to Sell
Step 3: @sales_order_follow_up submit SO-00752-LEGOSAN AB
        → Verify: SO submitted
Step 4: @manufacturing create wo from so SO-00752-LEGOSAN AB
        → Verify: Sales WO created with BOM-0307-001
Step 5: @manufacturing submit wo MFG-WO-YYYYY
        @manufacturing transfer materials MFG-WO-YYYYY
        @manufacturing manufacture MFG-WO-YYYYY
        → Verify: Labeled 0307 in FG to Sell
Step 6: @sales_order_follow_up delivery SO-00752-LEGOSAN AB
        → Verify: DN created and submitted
Step 7: @sales_order_follow_up invoice SO-00752-LEGOSAN AB
        → Verify: SI created, CFDI G03, USD currency
Step 8: @payment create [SI-NAME]
        @payment submit [PE-NAME]
        → Verify: PE created, SI outstanding = 0
```

**Verification:**
- `@workflow status SO-00752-LEGOSAN AB` → All 8 steps ✅
- All documents linked in correct chain
- Stock balances correct

### INT-002: Orchestrator Full Run
**Input:** `@workflow run SO-00752-LEGOSAN AB mfg-bom BOM-0307-005 sales-bom BOM-0307-001`
**Expected:** Same result as INT-001 but automated

### INT-003: Item Mismatch Detection
**Scenario:** SO has item 0307, but someone tries to use a BOM for item 0227
**Expected:**
- Error caught: "BOM item does not match SO item"
- No incorrect WO created

---

## Phase 6: Router Integration Tests

### RTR-001: @manufacturing Routing
**Input (in Raven):** `@manufacturing help`
**Expected:** ManufacturingAgent.process_command receives "help"

### RTR-002: @payment Routing
**Input (in Raven):** `@payment outstanding`
**Expected:** PaymentAgent.process_command receives "outstanding"

### RTR-003: @workflow Routing
**Input (in Raven):** `@workflow status SO-00752-LEGOSAN AB`
**Expected:** WorkflowOrchestrator.process_command receives the message

### RTR-004: @ai Backward Compatibility
**Input (in Raven):** `@ai help`
**Expected:** Still routes to RaymondLucyAgent (no regression)

### RTR-005: @sales_order_follow_up Updated Commands
**Input (in Raven):** `@sales_order_follow_up delivery SO-00752-LEGOSAN AB`
**Expected:** Updated agent handles the new "delivery" command

---

## Phase 7: Edge Cases & Error Handling

### EDGE-001: Double Submit Protection
Submit same WO twice → second call returns "already submitted"

### EDGE-002: Cancelled Document Handling
Try to create DN from cancelled SO → returns error

### EDGE-003: Missing Label Stock
Labels not in stock → manufacture step fails with clear error

### EDGE-004: Multi-Currency Handling
SI created with USD currency, company is MXN → conversion rate applied

### EDGE-005: Server Script Safety
None of the agent code uses `import frappe` in Server Script context

### EDGE-006: No import frappe in Server Scripts
Verify all agent files use `import frappe` at module level only,
and any Server Script hooks use `frappe` from the global scope

---

## Execution Order

| Phase | Tests | Priority | Pre-requisites |
|-------|-------|----------|----------------|
| 1. Manufacturing Agent | MFG-001 to MFG-012 | HIGH | BOM-0307-005 submitted |
| 2. Sales Order Follow-up | SO-001 to SO-010 | HIGH | Phase 1 complete |
| 3. Payment Agent | PAY-001 to PAY-007 | MEDIUM | Phase 2 complete (need SI) |
| 4. Workflow Orchestrator | WF-001 to WF-005 | MEDIUM | Phases 1-3 complete |
| 5. Integration | INT-001 to INT-003 | HIGH | All phases complete |
| 6. Router | RTR-001 to RTR-005 | HIGH | Router patch applied |
| 7. Edge Cases | EDGE-001 to EDGE-006 | LOW | All phases complete |

**Total Tests: 46**

---

## Files Delivered

| File | Location | Action |
|------|----------|--------|
| `manufacturing_agent.py` | `raven_ai_agent/agents/` | NEW |
| `payment_agent.py` | `raven_ai_agent/agents/` | NEW |
| `workflow_orchestrator.py` | `raven_ai_agent/agents/` | NEW |
| `sales_order_followup_agent.py` | `raven_ai_agent/agents/` | UPDATED |
| `__init__.py` | `raven_ai_agent/agents/` | UPDATED |
| `router.py` (patch) | `raven_ai_agent/api/handlers/` | PATCH (add routing blocks) |
| `TEST_PLAN.md` | `docs/project_formulation/` | NEW |

---

## Sign-off

- [ ] Phase 1 passed
- [ ] Phase 2 passed
- [ ] Phase 3 passed
- [ ] Phase 4 passed
- [ ] Phase 5 passed (integration)
- [ ] Phase 6 passed (router)
- [ ] Phase 7 passed (edge cases)
- [ ] All 46 tests passed
- [ ] Ready for production
