"""
BUG 90 Validation Script
Tests the @ai pipeline command to verify it returns real ERPNext data, not placeholders.

Run with: bench execute raven_ai_agent.bug90_test.run_tests
"""

import frappe
import json
from raven_ai_agent.agents.task_validator import TaskValidator


def test_pipeline_valid_quotation():
    """Test pipeline with a valid quotation - should return real data"""
    print("=" * 60)
    print("TEST 1: Valid Quotation Pipeline")
    print("=" * 60)
    
    # Get a list of existing quotations
    quotations = frappe.get_list("Quotation", filters={"docstatus": 1}, 
                                  fields=["name", "customer", "grand_total", "status"],
                                  limit=5)
    
    if not quotations:
        print("❌ No submitted quotations found in system!")
        return
    
    print(f"Found {len(quotations)} submitted quotations")
    
    # Test with first available quotation
    qtn = quotations[0]
    qtn_name = qtn.name
    
    print(f"\nTesting with: {qtn_name}")
    print(f"  Customer: {qtn.customer}")
    print(f"  Total: {qtn.grand_total}")
    print(f"  Status: {qtn.status}")
    
    validator = TaskValidator()
    result = validator.handle(f"@ai pipeline {qtn_name}", None)
    
    print(f"\nResult: {json.dumps(result, indent=2)[:500]}...")
    
    # Check for placeholders
    response_text = result.get("message", "") or result.get("response", "")
    
    has_placeholder = "[Customer Name]" in response_text or "[Amount]" in response_text
    
    if result.get("success"):
        if has_placeholder:
            print("\n❌ FAIL: Response contains placeholders!")
        else:
            print("\n✅ PASS: Response contains real data!")
    else:
        print(f"\n⚠️ Command failed: {result.get('error')}")


def test_pipeline_invalid_quotation():
    """Test pipeline with an invalid quotation ID - should return clean error"""
    print("\n" + "=" * 60)
    print("TEST 2: Invalid Quotation ID")
    print("=" * 60)
    
    validator = TaskValidator()
    result = validator.handle("@ai pipeline SAL-QTN-INVALID-99999", None)
    
    print(f"Result: {json.dumps(result, indent=2)}")
    
    if not result.get("success") and result.get("error"):
        print("\n✅ PASS: Clean error returned for invalid ID")
    else:
        print("\n❌ FAIL: Should have returned error for invalid ID")


def test_multiple_quotations():
    """Test pipeline with multiple valid quotations"""
    print("\n" + "=" * 60)
    print("TEST 3: Multiple Valid Quotations")
    print("=" * 60)
    
    quotations = frappe.get_list("Quotation", 
                                  filters={"docstatus": ["!=", 2]},
                                  fields=["name"],
                                  limit=3)
    
    if len(quotations) < 2:
        print("Not enough quotations to test multiple")
        return
    
    validator = TaskValidator()
    
    success_count = 0
    placeholder_count = 0
    
    for qtn in quotations:
        qtn_name = qtn.name
        print(f"\nTesting: {qtn_name}")
        
        result = validator.handle(f"@ai pipeline {qtn_name}", None)
        
        if result.get("success"):
            success_count += 1
            response_text = result.get("message", "") or result.get("response", "")
            if "[Customer Name]" in response_text or "[Amount]" in response_text:
                placeholder_count += 1
                print("  ⚠️ Contains placeholders")
            else:
                print("  ✅ Contains real data")
        else:
            print(f"  ❌ Failed: {result.get('error')}")
    
    print(f"\nResults: {success_count}/{len(quotations)} succeeded, {placeholder_count} with placeholders")
    
    if success_count > 0 and placeholder_count == 0:
        print("✅ PASS: All valid quotations return real data")
    else:
        print("❌ FAIL: Some issues found")


def run_tests():
    """Run all BUG 90 validation tests"""
    print("BUG 90 VALIDATION TESTS")
    print("=" * 60)
    
    try:
        test_pipeline_valid_quotation()
    except Exception as e:
        print(f"Test 1 Error: {e}")
    
    try:
        test_pipeline_invalid_quotation()
    except Exception as e:
        print(f"Test 2 Error: {e}")
    
    try:
        test_multiple_quotations()
    except Exception as e:
        print(f"Test 3 Error: {e}")
    
    print("\n" + "=" * 60)
    print("TESTS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    run_tests()