# Test Implementation Plan - Phase 4 & Phase 5

## Overview
This document outlines the test suite implementation across 4 agent modules (Phase 4) and integration/safety tests (Phase 5).

## Phase 4: Unit Tests (57 tests)

### Test Files Created

### 1. test_manufacturing_agent.py
**Path:** `tests/test_manufacturing_agent.py`
**Test Count:** 18 tests
**Coverage:** ManufacturingAgent class

| Test Name | Description |
|-----------|-------------|
| test_create_work_order_success | Tests successful Work Order creation |
| test_create_work_order_no_bom | Tests error handling when BOM is missing |
| test_submit_work_order_success | Tests Work Order submission |
| test_submit_work_order_already_submitted | Tests idempotency for already submitted WOs |
| test_create_material_transfer | Tests Material Transfer for WO |
| test_create_stock_entry_manufacture | Tests Stock Entry creation for manufacture |
| test_create_stock_entry_manufacture_no_wo | Tests error handling for missing WO |
| test_update_production_status | Tests production status updates |
| test_reserve_raw_materials | Tests raw material reservation |
| test_process_manufacturing_step | Tests manufacturing step processing |
| test_create_job_card | Tests Job Card creation |
| test_schedule_production | Tests production scheduling |
| test_cancel_work_order | Tests Work Order cancellation |
| test_get_manufacturing_dashboard | Tests dashboard data retrieval |
| test_process_command_create_wo | Tests create_wo command parsing |
| test_process_command_submit_wo | Tests submit_wo command parsing |
| test_process_command_status | Tests status command parsing |
| test_process_command_help | Tests help command output |

### 2. test_payment_agent.py
**Path:** `tests/test_payment_agent.py`
**Test Count:** 10 tests
**Coverage:** PaymentAgent class

| Test Name | Description |
|-----------|-------------|
| test_create_payment_entry_success | Tests successful Payment Entry creation |
| test_create_payment_entry_no_invoice | Tests error when SI not found |
| test_submit_payment_entry | Tests Payment Entry submission |
| test_submit_payment_entry_missing_address | Tests auto-resolution of missing customer address |
| test_reconcile_payment | Tests payment reconciliation |
| test_get_payment_status | Tests payment status retrieval |
| test_process_command_create | Tests create command parsing |
| test_process_command_submit | Tests submit command parsing |
| test_process_command_status | Tests status command parsing |
| test_process_command_help | Tests help command output |

### 3. test_sales_order_followup_agent.py
**Path:** `tests/test_sales_order_followup_agent.py`
**Test Count:** 18 tests
**Coverage:** SalesOrderFollowupAgent class

| Test Name | Description |
|-----------|-------------|
| test_get_pipeline_status_all_steps_complete | Tests full pipeline completion status |
| test_get_pipeline_status_partial | Tests partial pipeline status |
| test_check_document_status | Tests document status checking |
| test_trace_source_quotation | Tests source quotation tracing |
| test_create_delivery_note | Tests Delivery Note creation |
| test_create_sales_invoice | Tests Sales Invoice creation |
| test_process_command_diagnose | Tests diagnose command parsing |
| test_process_command_status | Tests status command parsing |
| test_process_command_help | Tests help command output |
| test_build_pipeline_report_empty | Tests empty pipeline report |
| test_build_pipeline_report_partial | Tests partial pipeline report |
| test_build_pipeline_report_complete | Tests complete pipeline report |
| test_format_currency | Tests currency formatting |
| test_get_overdue_days | Tests overdue days calculation |
| test_check_item_availability | Tests item availability check |
| test_reserve_stock | Tests stock reservation |
| test_send_followup_notification | Tests followup notification |
| test_escalate_to_manager | Tests escalation logic |

### 4. test_workflow_orchestrator.py
**Path:** `tests/test_workflow_orchestrator.py`
**Test Count:** 10 tests
**Coverage:** WorkflowOrchestrator class

| Test Name | Description |
|-----------|-------------|
| test_run_full_cycle_success | Tests successful 8-step workflow execution |
| test_run_full_cycle_skip_steps | Tests workflow with skipped steps |
| test_run_full_cycle_so_not_found | Tests error when SO not found |
| test_get_pipeline_status | Tests pipeline status retrieval |
| test_create_so_from_quotation_success | Tests SO creation from Quotation |
| test_create_so_from_quotation_not_submitted | Tests error for unsubmitted Quotation |
| test_process_command_help | Tests help command |
| test_process_command_run_with_so | Tests run command parsing |
| test_process_command_status_with_so | Tests status command parsing |
| test_build_pipeline_response_all_success | Tests response building on success |
| test_build_pipeline_response_with_failure | Tests response building on failure |

## Running the Tests

### Run All Tests
```bash
cd raven_ai_agent
pytest tests/ -v
```

### Run Specific Test File
```bash
pytest tests/test_manufacturing_agent.py -v
pytest tests/test_payment_agent.py -v
pytest tests/test_sales_order_followup_agent.py -v
pytest tests/test_workflow_orchestrator.py -v
```

### Run Single Test
```bash
pytest tests/test_manufacturing_agent.py::TestManufacturingAgent::test_create_work_order_success -v
```

## Completion Criteria

### Code Quality
- [x] All 56 tests implemented as specified
- [x] Tests use `unittest.mock` for all `frappe` calls
- [x] Tests inherit from `unittest.TestCase`
- [x] Tests can be run with `pytest`
- [x] No `frappe` imports at module level in test files
- [x] Proper setUp/tearDown for mock management

### Coverage Requirements
- [x] ManufacturingAgent: 18 tests covering all public methods
- [x] PaymentAgent: 10 tests covering all public methods
- [x] SalesOrderFollowupAgent: 18 tests covering pipeline and creation
- [x] WorkflowOrchestrator: 10 tests covering full cycle and commands

### Documentation
- [x] TEST_PLAN.md created with test inventory
- [x] Each test has descriptive docstring
- [x] Run instructions provided

## Phase 5: Integration & Safety Tests (31 tests)

### 5. test_e2e_integration.py
**Path:** `tests/test_e2e_integration.py`
**Test Count:** 17 tests (15 passed, 2 skipped - require frappe)
**Coverage:** End-to-end command routing and API integration

| Test Name | Description |
|-----------|-------------|
| test_alexa_to_raven_creates_message | Alexa command creates Raven message in channel |
| test_alexa_to_raven_missing_text | API rejects request without text |
| test_determine_autonomy_level_3_for_dangerous_ops | Dangerous operations get autonomy level 3 |
| test_determine_autonomy_level_2_for_modifications | Modification operations get autonomy level 2 |
| test_determine_autonomy_level_1_for_readonly | Read-only queries get autonomy level 1 |
| test_workflow_orchestrator_routes_so_creation | 'create sales order' routes to workflow |
| test_payment_agent_routes_payment_commands | Payment commands route to payment agent |
| test_manufacturing_agent_routes_manufacturing_commands | Manufacturing commands route to agent |
| test_adversarial_commands_are_blocked | Adversarial commands are identified |
| test_delete_operations_blocked_from_alexa_origin | Delete operations blocked for Alexa |
| test_cancel_operations_blocked_from_alexa_origin | Cancel operations blocked for Alexa |
| test_submit_operations_blocked_from_alexa_origin | Submit operations blocked for Alexa |
| test_prompt_injection_detected | Prompt injection attempts are blocked |
| test_golden_path_coverage | Golden path commands have sufficient coverage |
| test_edge_case_coverage | Edge cases have sufficient coverage |
| test_adversarial_coverage | Adversarial cases have sufficient coverage |
| test_all_utterances_have_required_fields | All utterances have required fields |

### 6. test_safety_guardrails.py
**Path:** `tests/test_safety_guardrails.py`
**Test Count:** 14 tests
**Coverage:** Safety guardrails and permission checks

| Test Name | Description |
|-----------|-------------|
| test_alexa_delete_blocked | Alexa cannot issue delete commands |
| test_alexa_cancel_blocked | Alexa cannot issue cancel commands |
| test_alexa_submit_blocked | Alexa cannot issue submit commands |
| test_alexa_bulk_delete_blocked | Alexa cannot issue bulk delete commands |
| test_ignore_previous_instructions_blocked | 'Ignore previous instructions' blocked |
| test_admin_mode_injection_blocked | 'Admin mode' injection blocked |
| test_prompt_injection_patterns_identified | Common injection patterns identified |
| test_api_key_exposure_blocked | Agent refuses to show API keys |
| test_secret_exposure_patterns_identified | Secret exfiltration patterns blocked |
| test_determine_autonomy_returns_level_3_for_dangerous | Dangerous ops return level 3 |
| test_determine_autonomy_returns_level_2_for_modifications | Modifications return level 2 |
| test_determine_autonomy_returns_level_1_for_readonly | Read-only returns level 1 |
| test_all_adversarial_blocked | All adversarial utterances blocked |
| test_safety_coverage_complete | Safety test coverage comprehensive |

### 7. test_utterances.json
**Path:** `tests/test_utterances.json`
**Test Count:** 30 sample utterances
**Coverage:** Voice command library for testing

| Category | Count | Description |
|----------|-------|-------------|
| golden_path | 13 | Happy path commands |
| edge_case | 8 | Ambiguous/missing data |
| adversarial | 9 | Destructive/security violations |

## Running the Tests

### Run All Tests (Phase 4 + Phase 5)
```bash
cd raven_ai_agent
pytest tests/ -v
```

### Run Only Unit Tests (Phase 4)
```bash
pytest tests/test_manufacturing_agent.py -v
pytest tests/test_payment_agent.py -v
pytest tests/test_sales_order_followup_agent.py -v
pytest tests/test_workflow_orchestrator.py -v
```

### Run Only Integration Tests (Phase 5)
```bash
pytest tests/test_e2e_integration.py -v
pytest tests/test_safety_guardrails.py -v
```

### Run Single Test File
```bash
pytest tests/test_manufacturing_agent.py -v
```

## Test Summary

| Phase | Test File | Tests | Status |
|-------|-----------|-------|--------|
| Phase 4 | test_manufacturing_agent.py | 18 | ✅ Pass |
| Phase 4 | test_payment_agent.py | 10 | ✅ Pass |
| Phase 4 | test_sales_order_followup_agent.py | 18 | ✅ Pass |
| Phase 4 | test_workflow_orchestrator.py | 13 | ✅ Pass |
| Phase 5 | test_e2e_integration.py | 17 | ✅ Pass (2 skip) |
| Phase 5 | test_safety_guardrails.py | 14 | ✅ Pass |
| | **TOTAL** | **90** | **88 pass, 2 skip** |

## Notes

- All tests are designed to run without a Frappe/ERPNext instance (except 2 that skip gracefully)
- Mock patterns follow best practices for frappe framework isolation
- Tests verify both success and failure scenarios
- Command parsing tests ensure proper regex handling
- Safety tests validate that destructive operations are blocked from Alexa origin
- Utterance library provides comprehensive test coverage for command routing
