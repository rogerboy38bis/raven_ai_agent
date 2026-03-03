# Raven AI Agent — 8-Step Workflow Implementation Plan

**Version:** 2.0  
**Date:** 2026-03-03  
**Author:** Orchestrator + RPD  
**Repo:** [github.com/rogerboy38/raven_ai_agent](https://github.com/rogerboy38/raven_ai_agent)  
**Site:** erp.sysmayal2.cloud  
**Pilot:** MFG-WO-03726 / SO-00752-LEGOSAN AB / BOM-0307-005

---

## 1. Architecture Overview

### 1.1 The 8-Step Workflow

```
Quotation → SO → WO (Mix) → SE (Manufacture) → Sales WO → SE (Sales) → DN → SI → PE
             ↑ Step 3  ↑ Step 1    ↑ Step 2      ↑ Step 4   ↑ Step 5   ↑6  ↑7  ↑8
```

| Step | Action                      | Document       | Agent              |
|------|-----------------------------|----------------|--------------------|
| 0    | Quotation → SO              | Sales Order    | SalesOrderFollowup |
| 1    | WO (Manufacturing) → Submit | Work Order     | Manufacturing      |
| 2    | Stock Entry (Manufacture)   | Stock Entry    | Manufacturing      |
| 3    | SO → Submit                 | Sales Order    | SalesOrderFollowup |
| 4    | Sales WO from SO            | Work Order     | Manufacturing      |
| 5    | SE (Manufacture for Sales)  | Stock Entry    | Manufacturing      |
| 6    | Delivery Note               | Delivery Note  | SalesOrderFollowup |
| 7    | Sales Invoice (CFDI)        | Sales Invoice  | SalesOrderFollowup |
| 8    | Payment Entry               | Payment Entry  | Payment            |

### 1.2 File Map

```
raven_ai_agent/agents/
├── __init__.py                        ← UPDATED (registers 3 new agents)
├── bom_creator_agent.py               ← EXISTING (no changes)
├── sales_order_followup_agent.py      ← UPDATED (+create_delivery_note, +create_sales_invoice, +create_from_quotation)
├── manufacturing_agent.py             ← NEW (Steps 1, 2, 4, 5)
├── payment_agent.py                   ← NEW (Step 8)
├── workflow_orchestrator.py           ← NEW (Full pipeline controller)
├── rnd_agent.py                       ← EXISTING (no changes)
├── iot_agent.py                       ← EXISTING (no changes)
└── executive_agent.py                 ← EXISTING (no changes)
```

### 1.3 BOM Hierarchy (AMB-Wellness Powder Products)

```
LEVEL 5 — SALES           BOM-0307-001  (0307 + LBL0307)           → FG to Sell
LEVEL 4 — MIX PLANT       BOM-0307-005  (ITEM_0612185231 + LBL4INX6INBL)  → WIP in Mix
LEVEL 3 — FORMULATION     BOM-0612..    (0301/0302/0303 + ingredients)
LEVEL 2 — DRY PLANT       BOM-030X      (0227 + drums + labels)
LEVEL 1 — JUICE PLANT     BOM-0227      (M033 Aloe Leaf + supplies)
```

Sales team only sees Level 5. Manufacturing handles Levels 1-4 internally.

---

## 2. New Files — Detailed Specification

### 2.1 manufacturing_agent.py (729 lines)

**Class:** `ManufacturingAgent`

| Method                                 | Purpose                                    | ERPNext API Used                          |
|----------------------------------------|--------------------------------------------|-------------------------------------------|
| `create_work_order()`                  | Create WO from BOM + qty                   | `frappe.new_doc("Work Order")`            |
| `submit_work_order()`                  | Submit WO (Draft → Submitted)              | `wo.submit()`                             |
| `create_stock_entry_manufacture()`     | SE type "Manufacture" from WO              | `make_stock_entry(wo, "Manufacture")`     |
| `create_material_transfer_for_manufacture()` | Transfer materials to WIP              | `make_stock_entry(wo, "Material Transfer")` |
| `create_work_order_from_so()`          | Create WO(s) from SO items + BOM lookup    | BOM lookup + `create_work_order()`        |
| `get_wo_status()`                      | Status + linked SEs + next action          | `frappe.get_doc("Work Order")`            |
| `get_work_orders_for_so()`             | List all WOs linked to an SO               | `frappe.get_all("Work Order")`            |
| `_get_bom_for_level()`                 | BOM routing: sales/mix/production          | Pattern: `BOM-{item}-001/005/006`         |
| `_get_wip_warehouse()`                 | Auto-detect WIP (Mix BOM → WIP in Mix)     | `frappe.db.get_value("Warehouse")`        |
| `process_command()`                    | NL command router                          | Regex + method dispatch                   |

**Key intelligence:**
- Auto-detects BOM level (sales `-001`, mix `-005`, production `-006`)
- WIP warehouse varies by BOM type (Mix → "WIP in Mix", others → default)
- Idempotent: checks for existing draft WOs before creating duplicates
- Confirmation flow: preview → confirm → execute

### 2.2 sales_order_followup_agent.py (770 lines, UPDATED)

**Class:** `SalesOrderFollowupAgent`

| Method (NEW)               | Purpose                                     | ERPNext API Used                              |
|----------------------------|---------------------------------------------|-----------------------------------------------|
| `create_from_quotation()`  | Convert Quotation → SO (Step 3)             | `make_sales_order(quotation_name)`            |
| `create_delivery_note()`   | Auto-create DN from SO (Step 6)             | `make_delivery_note(so_name)`                 |
| `create_sales_invoice()`   | Auto-create SI with CFDI fields (Step 7)    | `make_sales_invoice(so_name or dn_name)`      |

**CFDI compliance (Step 7):**
- `mx_cfdi_use` → G03 (Gastos en general) — default for export customers
- `mx_payment_method` → PUE (single payment) or PPD (partial)
- `custom_customer_invoice_currency` → from SO currency (USD/MXN)
- `conversion_rate` → from SO for multi-currency
- Handles SAT Tax Regime 601 + RFC XAXX010101000 for foreign customers

**Updated logic:**
- `STATUS_NEXT_ACTIONS` now includes manufacturing steps
- `get_next_steps()` checks for active Work Orders before recommending DN
- `get_so_status()` includes linked Work Orders with progress %
- Inventory check warns about manufacturing when stock is insufficient

### 2.3 payment_agent.py (347 lines)

**Class:** `PaymentAgent`

| Method                     | Purpose                                     | ERPNext API Used                              |
|----------------------------|---------------------------------------------|-----------------------------------------------|
| `create_payment_entry()`   | Create PE from Sales Invoice                | `get_payment_entry("Sales Invoice", si)`      |
| `submit_payment_entry()`   | Submit PE                                   | `pe.submit()`                                 |
| `reconcile_payment()`      | Verify PE ↔ SI reconciliation               | Check `outstanding_amount` on SI              |
| `get_unpaid_invoices()`    | List unpaid SIs                             | `frappe.get_all("Sales Invoice")`             |

**Multi-currency handling:**
- USD invoices on MXN company: applies `conversion_rate` from SI
- Auto-detects bank account from Mode of Payment + Company

### 2.4 workflow_orchestrator.py (668 lines)

**Class:** `WorkflowOrchestrator`

| Method                          | Purpose                                        |
|---------------------------------|------------------------------------------------|
| `run_full_cycle()`              | Execute all 8 steps (or from Quotation)        |
| `get_pipeline_status()`         | Dashboard: where is each SO in the pipeline?   |
| `validate_item_consistency()`   | Catch item 0307 vs 0227 mismatch              |
| `_execute_pipeline()`           | Step-by-step execution with state checks       |
| `_get_next_step()`              | Determine what to do next                      |

**Key intelligence:**
- Classifies WOs as "mix-level" (BOM-xxx-005) vs "sales-level" (BOM-xxx-001)
- Checks inventory before creating DN (blocks if insufficient)
- Validates manufactured item matches SO item (prevents 0307/0227 mismatch)
- Dry-run mode: analyzes without creating documents
- Idempotent throughout: every step checks for existing docs first

### 2.5 __init__.py (30 lines, UPDATED)

Registers all 7 agents in `__all__`:
```python
__all__ = [
    "BOMCreatorAgent",
    "SalesOrderFollowupAgent",  # updated
    "ManufacturingAgent",       # new
    "PaymentAgent",             # new
    "WorkflowOrchestrator",     # new
    "RndAgent",
    "IoTAgent",
]
```

---

## 3. Test Plan

### 3.1 Test Strategy

| Level         | Tool                      | Scope                                    |
|---------------|---------------------------|------------------------------------------|
| Unit Tests    | `pytest` + `unittest.mock`| Each method in isolation, mocked frappe   |
| Integration   | `bench --site ... console`| Real ERPNext docs on sandbox              |
| E2E           | Raven channel `@ai` cmds  | Full NL command → response via Raven      |
| Regression    | Pilot re-run              | Re-execute MFG-WO-03726 flow end-to-end  |

### 3.2 Unit Tests — manufacturing_agent.py

| ID    | Test                                          | Input                                     | Expected                                  | Priority |
|-------|-----------------------------------------------|-------------------------------------------|-------------------------------------------|----------|
| M-01  | Create WO with valid BOM                      | item=0307, qty=150, bom=BOM-0307-005      | WO created, status=Draft                  | P0       |
| M-02  | Create WO — no BOM found                      | item=NONEXISTENT, qty=10                  | Error: "No active BOM found"              | P0       |
| M-03  | Create WO — idempotent (existing draft)       | Same params as M-01, run twice            | Returns existing WO, no duplicate         | P0       |
| M-04  | Submit WO — happy path                        | wo=MFG-WO-XXXXX (draft)                   | docstatus=1                               | P0       |
| M-05  | Submit WO — already submitted                 | wo=MFG-WO-XXXXX (submitted)               | Message: "already submitted"              | P1       |
| M-06  | Submit WO — cancelled                         | wo=MFG-WO-XXXXX (cancelled)               | Error: "is cancelled"                     | P1       |
| M-07  | Create SE Manufacture — no material transferred| wo with 0 transferred                     | Error: "No materials transferred"         | P0       |
| M-08  | Create SE Manufacture — happy path            | wo with materials transferred              | SE created, purpose=Manufacture           | P0       |
| M-09  | Create SE Manufacture — WO already completed  | wo.status=Completed                        | Message: "already completed"              | P1       |
| M-10  | Create Material Transfer                      | wo submitted, materials available           | SE created, purpose=Material Transfer     | P0       |
| M-11  | Create WO from SO — sales level               | so=SO-00752, level=sales                   | WO with BOM-0307-001                      | P0       |
| M-12  | Create WO from SO — mix level                 | so=SO-00752, level=mix                     | WO with BOM-0307-005                      | P0       |
| M-13  | Create WO from SO — SO not submitted          | so (draft)                                 | Error: "must be submitted"                | P1       |
| M-14  | _get_bom_for_level — sales                    | item=0307, level=sales                     | BOM-0307-001                              | P1       |
| M-15  | _get_bom_for_level — mix                      | item=0307, level=mix                       | BOM-0307-005                              | P1       |
| M-16  | _get_wip_warehouse — mix BOM                  | bom=BOM-0307-005                           | "WIP in Mix - AMB-W"                      | P1       |
| M-17  | Confirm flow — preview then execute           | confirm=False then confirm=True            | First returns preview, second creates doc | P1       |
| M-18  | process_command — "create work order 0307 150 Kg" | NL message                            | Calls create_work_order with parsed args  | P2       |

### 3.3 Unit Tests — sales_order_followup_agent.py (NEW methods only)

| ID    | Test                                          | Input                                     | Expected                                  | Priority |
|-------|-----------------------------------------------|-------------------------------------------|-------------------------------------------|----------|
| S-01  | create_from_quotation — happy path            | qtn submitted                              | SO created, linked to quotation           | P0       |
| S-02  | create_from_quotation — idempotent            | qtn that already has SO                    | Returns existing SO                       | P0       |
| S-03  | create_from_quotation — qtn not submitted     | qtn.docstatus=0                            | Error: "must be submitted"                | P1       |
| S-04  | create_delivery_note — happy path             | SO submitted, inventory available           | DN created in Draft                       | P0       |
| S-05  | create_delivery_note — idempotent             | SO that already has DN                      | Returns existing DN                       | P0       |
| S-06  | create_delivery_note — insufficient inventory | SO with items not in stock                  | Error: "Insufficient inventory"           | P0       |
| S-07  | create_delivery_note — SO not submitted       | so.docstatus=0                              | Error: "must be submitted"                | P1       |
| S-08  | create_delivery_note — already delivered      | so.delivery_status="Fully Delivered"        | Message: "already fully delivered"        | P1       |
| S-09  | create_delivery_note — QI warning             | Item has inspection_required_before_delivery| DN created + QI warning in message        | P1       |
| S-10  | create_sales_invoice — from DN                | SO with submitted DN                        | SI created via DN path, CFDI fields set   | P0       |
| S-11  | create_sales_invoice — from SO directly       | SO without DN                               | SI created via SO path                    | P0       |
| S-12  | create_sales_invoice — idempotent             | SO that already has SI                      | Returns existing SI                       | P0       |
| S-13  | create_sales_invoice — CFDI G03               | cfdi_use=G03                                | si.mx_cfdi_use = "G03"                    | P0       |
| S-14  | create_sales_invoice — USD currency           | SO in USD on MXN company                    | si.currency=USD, conversion_rate from SO  | P0       |
| S-15  | create_sales_invoice — fully billed           | so.billing_status="Fully Billed"            | Message: "already fully billed"           | P1       |
| S-16  | get_next_steps — with active WOs              | SO has WOs in progress                      | Steps mention completing WOs first        | P1       |
| S-17  | get_next_steps — inventory available          | SO with stock in FG to Sell                 | Steps recommend creating DN               | P1       |
| S-18  | get_so_status — includes WOs                  | SO with linked Work Orders                  | Response includes work_orders list         | P1       |

### 3.4 Unit Tests — payment_agent.py

| ID    | Test                                          | Input                                     | Expected                                  | Priority |
|-------|-----------------------------------------------|-------------------------------------------|-------------------------------------------|----------|
| P-01  | create_payment_entry — happy path             | SI submitted, outstanding > 0              | PE created in Draft                       | P0       |
| P-02  | create_payment_entry — idempotent             | SI that already has PE                      | Returns existing PE                       | P0       |
| P-03  | create_payment_entry — SI not submitted       | si.docstatus=0                              | Error: "must be submitted"                | P1       |
| P-04  | create_payment_entry — fully paid             | si.outstanding_amount=0                     | Message: "already fully paid"             | P1       |
| P-05  | create_payment_entry — USD multi-currency     | SI in USD, company in MXN                   | PE with conversion_rate applied           | P0       |
| P-06  | submit_payment_entry — happy path             | PE in draft                                 | PE submitted                              | P0       |
| P-07  | reconcile_payment — fully reconciled          | PE submitted, SI outstanding=0              | fully_reconciled=True                     | P0       |
| P-08  | reconcile_payment — partial                   | PE submitted, SI still has outstanding      | fully_reconciled=False                    | P1       |
| P-09  | get_unpaid_invoices                           | Multiple unpaid SIs exist                   | Returns list sorted by due_date           | P1       |
| P-10  | _get_bank_account                             | company + mode_of_payment                   | Returns correct GL account                | P2       |

### 3.5 Unit Tests — workflow_orchestrator.py

| ID    | Test                                          | Input                                     | Expected                                  | Priority |
|-------|-----------------------------------------------|-------------------------------------------|-------------------------------------------|----------|
| O-01  | get_pipeline_status — all steps               | SO with full history                        | All 8 steps shown with status             | P0       |
| O-02  | get_pipeline_status — fresh SO                | SO just submitted, no WOs/DN/SI             | Steps 3 done, rest pending                | P0       |
| O-03  | run_full_cycle — dry run                      | so_name, dry_run=True                       | All steps analyzed, nothing created        | P0       |
| O-04  | run_full_cycle — from quotation               | quotation_name (submitted)                  | Creates SO first, then runs pipeline       | P0       |
| O-05  | validate_item_consistency — no mismatch       | SO items match WO production items          | is_valid=True                             | P0       |
| O-06  | validate_item_consistency — mismatch          | WO BOM produces wrong item                  | is_valid=False, issues list               | P0       |
| O-07  | _get_next_step — identifies correct step      | Various partial completion states            | Returns correct next step number           | P1       |
| O-08  | run_full_cycle — idempotent re-run            | SO already at step 6                         | Steps 1-5 show "already_done"             | P1       |
| O-09  | run_full_cycle — blocked by inventory         | Step 6 blocked (no stock)                    | Step 6 status="blocked"                   | P1       |
| O-10  | _build_pipeline_preview                       | SO with mixed state                          | Readable markdown with ✅/⏳ icons          | P2       |

### 3.6 Integration Tests (bench console)

Run on sandbox `v2.sysmayal.cloud`:

```python
# ============================================================
# TEST: Full 8-step pipeline on sandbox
# ============================================================
# Pre-requisites:
#   - Item 0307 exists with active BOMs (-001, -005)
#   - ITEM_0612185231 has stock in FG to Sell (≥ 150 Kg)
#   - LBL4INX6INBL and LBL0307 have stock
#   - Customer LEGOSAN AB exists with tax regime 601

bench --site v2.sysmayal.cloud console

import frappe

# --- Step 1: Manufacturing Agent ---
from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
mfg = ManufacturingAgent()

# Test: Create Mix WO
result = mfg.create_work_order("0307", 150, bom="BOM-0307-005", confirm=True)
assert result["success"], f"Failed: {result}"
wo_mix = result["work_order"]
print(f"Mix WO: {wo_mix}")

# Test: Submit
result = mfg.submit_work_order(wo_mix, confirm=True)
assert result["success"], f"Failed: {result}"

# Test: Material Transfer
result = mfg.create_material_transfer_for_manufacture(wo_mix, confirm=True)
assert result["success"], f"Failed: {result}"
se_transfer = result["stock_entry"]
# Submit the SE manually
frappe.get_doc("Stock Entry", se_transfer).submit()
frappe.db.commit()

# Test: Manufacture
result = mfg.create_stock_entry_manufacture(wo_mix, confirm=True)
assert result["success"], f"Failed: {result}"
se_mfg = result["stock_entry"]
# Submit
frappe.get_doc("Stock Entry", se_mfg).submit()
frappe.db.commit()

# Test: Status
result = mfg.get_wo_status(wo_mix)
assert result["status"] == "Completed"
print(f"✅ Steps 1-2 passed: {wo_mix} completed")

# --- Step 3: Sales Agent ---
from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
sales = SalesOrderFollowupAgent()

# Use existing SO-00752 or create from quotation
so_name = "SO-00752-LEGOSAN AB"  # adjust to your test SO
result = sales.get_so_status(so_name)
assert result["success"]
print(f"SO status: {result['status']}")

# --- Step 4: Sales WO ---
result = mfg.create_work_order_from_so(so_name, bom_level="sales", confirm=True)
print(f"Sales WO result: {result}")

# --- Step 6: Delivery Note ---
result = sales.create_delivery_note(so_name, confirm=True)
print(f"DN result: {result}")

# --- Step 7: Sales Invoice ---
result = sales.create_sales_invoice(so_name, cfdi_use="G03", confirm=True)
print(f"SI result: {result}")

# --- Step 8: Payment ---
from raven_ai_agent.agents.payment_agent import PaymentAgent
pay = PaymentAgent()

if result.get("sales_invoice"):
    pe_result = pay.create_payment_entry(result["sales_invoice"], confirm=True)
    print(f"PE result: {pe_result}")

# --- Orchestrator Dashboard ---
from raven_ai_agent.agents.workflow_orchestrator import WorkflowOrchestrator
orch = WorkflowOrchestrator()

status = orch.get_pipeline_status(so_name)
print(f"Pipeline: {status['progress']}")
print(f"Next: {status['next_step']}")

print("\n✅ ALL INTEGRATION TESTS PASSED")
```

### 3.7 E2E Tests (Raven Channel)

Test via `@ai` commands in the Raven channel:

| ID    | Raven Command                                      | Expected Response                          |
|-------|----------------------------------------------------|--------------------------------------------|
| E-01  | `@ai create work order 0307 150 Kg`               | Preview with item/qty/BOM table            |
| E-02  | `@ai confirm create work order 0307 150 Kg`       | "✅ Work Order MFG-WO-XXXXX created"       |
| E-03  | `@ai status MFG-WO-03726`                         | Status details with next action            |
| E-04  | `@ai create work order from SO-00752 mix`          | Preview of mix-level WO creation           |
| E-05  | `@ai create DN from SO-00752`                      | DN preview or "insufficient inventory"     |
| E-06  | `@ai create invoice for SO-00752`                  | SI preview with CFDI fields                |
| E-07  | `@ai create payment for ACC-SINV-2026-00001`       | PE preview with amount                     |
| E-08  | `@ai pipeline status SO-00752`                     | 8-step dashboard with ✅/⏳                  |
| E-09  | `@ai dry run full cycle SO-00752`                  | Analysis without execution                 |
| E-10  | `@ai validate SO-00752`                            | Item consistency check                     |
| E-11  | `@ai unpaid invoices`                              | List of outstanding SIs                    |
| E-12  | `@ai pending orders`                               | List of pending SOs                        |

---

## 4. Implementation Phases

### Phase 1: Core Agents (Week 1)

**Deliverables:**
- [x] `manufacturing_agent.py` — 729 lines
- [x] `payment_agent.py` — 347 lines
- [x] `workflow_orchestrator.py` — 668 lines
- [x] Updated `sales_order_followup_agent.py` — 770 lines
- [x] Updated `__init__.py` — 30 lines

**Deployment:**
1. Copy files to `raven_ai_agent/agents/`
2. `bench get-app raven_ai_agent` (or `git pull` on server)
3. `bench --site erp.sysmayal2.cloud migrate`
4. `docker restart erpnext-backend-1` (if Docker)

### Phase 2: Unit Tests (Week 1-2)

**Deliverables:**
- [ ] `tests/test_manufacturing_agent.py` — 18 tests
- [ ] `tests/test_sales_order_updated.py` — 18 tests
- [ ] `tests/test_payment_agent.py` — 10 tests
- [ ] `tests/test_workflow_orchestrator.py` — 10 tests

**Total: 56 unit tests**

Run: `bench --site v2.sysmayal.cloud run-tests --app raven_ai_agent --module tests`

### Phase 3: Integration Testing (Week 2)

**Deliverables:**
- [ ] Integration test script (bench console)
- [ ] Test on sandbox with real data (item 0307, SO-00752 pattern)
- [ ] Fix any issues found during integration

**Pilot sequence:**
1. Create test SO (or use existing migration SO)
2. Run `orch.run_full_cycle(so_name, dry_run=True)` — verify plan
3. Run `orch.run_full_cycle(so_name, dry_run=False, confirm=True)` — execute
4. Verify all 8 documents created correctly

### Phase 4: Raven Channel Integration (Week 2-3)

**Deliverables:**
- [ ] Register agents in `api/agent_v2.py` command router
- [ ] Add manufacturing/payment/orchestrator intents to `gateway/router.py`
- [ ] Test all 12 E2E commands via Raven channel
- [ ] Update AGENTS.md documentation

### Phase 5: Production Deploy (Week 3)

**Deliverables:**
- [ ] Deploy to production server `srv1415373`
- [ ] Run regression: re-execute MFG-WO-03726 equivalent
- [ ] Monitor for 48 hours
- [ ] Update SOP document on Google Docs

---

## 5. Key Intelligence & Lessons Learned

### 5.1 From MFG-WO-03726 Pilot (2026-03-03)

| Issue Found                           | Fix Applied                                           | Agent Impact                          |
|---------------------------------------|-------------------------------------------------------|---------------------------------------|
| `source_warehouse` field name         | Changed `warehouse` → `source_warehouse` in queries   | Manufacturing: BOM item queries       |
| Workflow docstatus bug                | "Start" state doc_status 0→1                          | Manufacturing: submit_work_order      |
| Wrong target warehouse (WIP in Conc.) | Corrected to "WIP in Mix"                             | Manufacturing: _get_wip_warehouse     |
| Batch No mandatory on SE              | Agent must set batch_no from Bin query                 | Manufacturing: create_stock_entry     |
| Quality Inspection blocks DN submit   | Agent warns about QI requirement                       | Sales: create_delivery_note           |
| SAT CFDI Use permission error         | Added "All" role to SAT CFDI Use DocType               | Sales: create_sales_invoice           |
| Customer mx_tax_regime blank          | Bulk updated 450 customers to regime 601               | Sales: CFDI compliance                |
| No `import frappe` in Server Scripts  | All agents use frappe within Frappe context only        | All agents                            |
| Item 0307 self-reference in sales BOM | Separate WOs: mix level (-005) + sales level (-001)    | Manufacturing: _get_bom_for_level     |
| Workspace "Home" type missing         | Fixed in migration, not agent-related                  | Infrastructure                        |

### 5.2 Design Decisions

1. **Confirmation flow**: Every destructive action requires `confirm=True`. Default returns a preview.
2. **Idempotency**: Every create method checks for existing documents first.
3. **BOM level routing**: `-001` = sales, `-005` = mix, `-006` = production. Configurable per item.
4. **WIP warehouse routing**: Mix BOMs → "WIP in Mix", others → default WIP.
5. **Multi-currency**: USD invoices on MXN company handled via `conversion_rate` from SO.
6. **Agent isolation**: Each agent is self-contained. Orchestrator lazy-loads agents.

---

## 6. Raven Command Reference

### Manufacturing Agent
```
@ai create work order {item} {qty} Kg [bom=BOM-XXX]
@ai confirm create work order {item} {qty} Kg
@ai submit {MFG-WO-XXXXX}
@ai transfer materials for {MFG-WO-XXXXX}
@ai manufacture {MFG-WO-XXXXX}
@ai status {MFG-WO-XXXXX}
@ai create work order from {SO-XXXXX} [mix|sales]
@ai list work orders for {SO-XXXXX}
```

### Sales Order Agent (Updated)
```
@ai pending orders
@ai status {SO-XXXXX}
@ai inventory {SO-XXXXX}
@ai next steps {SO-XXXXX}
@ai create SO from {SAL-QTN-XXXXX}
@ai create DN from {SO-XXXXX}
@ai create invoice for {SO-XXXXX}
@ai track purchase {SO-XXXXX}
```

### Payment Agent
```
@ai create payment for {ACC-SINV-XXXXX}
@ai submit {ACC-PAY-XXXXX}
@ai reconcile {ACC-PAY-XXXXX}
@ai unpaid invoices
```

### Workflow Orchestrator
```
@ai pipeline status {SO-XXXXX}
@ai run full cycle {SO-XXXXX}
@ai dry run full cycle {SO-XXXXX}
@ai run full cycle from {SAL-QTN-XXXXX}
@ai validate {SO-XXXXX}
```

---

## 7. Phase Closure Criteria

| Phase | Criteria                                                              | Sign-off |
|-------|-----------------------------------------------------------------------|----------|
| 1     | All 5 files committed to `main` branch, no import errors             | [ ]      |
| 2     | 56 unit tests passing (`bench run-tests`)                            | [ ]      |
| 3     | Full 8-step pipeline runs on sandbox with real data                  | [ ]      |
| 4     | All 12 Raven commands working, AGENTS.md updated                     | [ ]      |
| 5     | Production deploy, 48h monitoring, SOP updated                       | [ ]      |
