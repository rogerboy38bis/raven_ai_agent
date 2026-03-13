"""
Data Quality Scanner - Diagnostic Script
Run this in bench console to validate fixes and understand the system

Usage:
    bench console
    exec(open('diagnose_scanner.py').read())
"""

import frappe
import json
from frappe.utils import nowdate, add_days

print("=" * 80)
print("DATA QUALITY SCANNER - DIAGNOSTIC SCRIPT")
print("=" * 80)

# ============================================================
# 1. TEST: Check Sales Order Fix Status
# ============================================================
print("\n### 1. CHECKING SALES ORDER FIX STATUS ###")

doc_name = "SO-00752-LEGOSAN AB"

try:
    so = frappe.get_doc("Sales Order", doc_name)
    print(f"\n📋 Sales Order: {so.name}")
    print(f"   Customer: {so.customer}")
    print(f"   Company: {so.company}")
    print(f"   Currency: {so.currency}")
    print(f"   Cost Center: {so.cost_center}")
    print(f"   Customer Address: {so.customer_address}")
    print(f"   Shipping Address: {so.shipping_address}")
    print(f"   Billing Address: {so.billing_address}")
    
    # Check if fix was applied
    if so.cost_center:
        print(f"\n✅ Cost Center FIX APPLIED: {so.cost_center}")
    else:
        print(f"\n❌ Cost Center NOT SET")
        
    if so.customer_address:
        print(f"✅ Customer Address FIX APPLIED: {so.customer_address}")
    else:
        print(f"❌ Customer Address NOT SET")
        
except frappe.DoesNotExistError:
    print(f"❌ Sales Order not found: {doc_name}")
except Exception as e:
    print(f"❌ Error: {e}")

# ============================================================
# 2. TEST: Check Address Records
# ============================================================
print("\n### 2. CHECKING ADDRESS RECORDS ###")

customer = "LEGOSAN AB"

# Get addresses for customer
addresses = frappe.get_all(
    "Dynamic Link",
    filters={"link_name": customer, "link_doctype": "Customer"},
    fields=["parent"],
    pluck="parent"
)

print(f"\n📍 Addresses linked to {customer}:")
if addresses:
    for addr_name in addresses:
        try:
            addr = frappe.get_doc("Address", addr_name)
            print(f"   - {addr.name}")
            print(f"     Type: {addr.address_type}")
            print(f"     Title: {addr.address_title}")
            print(f"     Phone: {addr.phone}")
            print(f"     City: {addr.city}")
        except:
            print(f"   - {addr_name} (error loading)")
else:
    print(f"   ❌ No addresses found!")

# ============================================================
# 3. TEST: Check Cost Centers
# ============================================================
print("\n### 3. CHECKING COST CENTERS ###")

# Check if our target CC exists
cc_name = "0612185231 - 0612185231 - AMB-W - AMB-W"

if frappe.db.exists("Cost Center", cc_name):
    cc = frappe.get_doc("Cost Center", cc_name)
    print(f"✅ Cost Center EXISTS: {cc.name}")
    print(f"   Company: {cc.company}")
    print(f"   Is Group: {cc.is_group}")
else:
    print(f"❌ Cost Center NOT FOUND: {cc_name}")

# Search for similar CCs
print(f"\n🔍 Searching for similar Cost Centers (containing '0612185231'):")
similar_ccs = frappe.get_all(
    "Cost Center",
    filters={"name": ["like", "%0612185231%"]},
    fields=["name", "company", "is_group"],
    limit=10
)

if similar_ccs:
    for cc in similar_ccs:
        print(f"   - {cc.name} (Group: {cc.is_group})")
else:
    print("   ❌ No similar cost centers found")

# ============================================================
# 4. TEST: Check Party Accounts (for Invoice Level)
# ============================================================
print("\n### 4. CHECKING PARTY ACCOUNTS (Customer → Account) ###")

# Get party accounts for LEGOSAN AB
party_accounts = frappe.get_all(
    "Party Account",
    filters={
        "parent": customer,
        "parenttype": "Customer"
    },
    fields=["name", "company", "account", "account_currency"]
)

print(f"\n💰 Party Accounts for {customer}:")
if party_accounts:
    for pa in party_accounts:
        # Check if account is group or leaf
        is_group = frappe.db.get_value("Account", pa.account, "is_group")
        print(f"   - Company: {pa.company}")
        print(f"     Account: {pa.account}")
        print(f"     Currency: {pa.account_currency}")
        print(f"     Is Group: {is_group}")
        if is_group:
            print(f"     ⚠️  WARNING: This is a GROUP account!")
else:
    print(f"   ❌ No party accounts configured!")

# ============================================================
# 5. TEST: Run Scanner Manually
# ============================================================
print("\n### 5. RUNNING SCANNER MANUALLY ###")

try:
    from raven_ai_agent.skills.data_quality_scanner.skill import DataQualityScannerSkill
    
    scanner = DataQualityScannerSkill()
    
    print(f"\n🔍 Running scan on {doc_name}...")
    result = scanner.scan_sales_order(doc_name)
    
    print(f"\n📊 Scan Results:")
    print(f"   Success: {result.get('success')}")
    print(f"   Issues Found: {result.get('total_issues')}")
    print(f"   Confidence: {result.get('confidence')}")
    print(f"   Can Proceed: {result.get('can_proceed')}")
    
    if result.get("issues"):
        print(f"\n📋 Issues:")
        for issue in result["issues"]:
            print(f"   [{issue.get('severity')}] {issue.get('message')}")
            print(f"      Field: {issue.get('field')}")
            print(f"      Auto-Fix: {issue.get('auto_fix')}")
    
except Exception as e:
    print(f"❌ Scanner Error: {e}")
    import traceback
    traceback.print_exc()

# ============================================================
# 6. TEST: Apply Address Fix Manually
# ============================================================
print("\n### 6. TESTING ADDRESS FIX ###")

def create_address_from_customer(customer):
    """Create address from customer details"""
    try:
        # Get customer
        cust = frappe.get_doc("Customer", customer)
        
        # Check existing addresses
        addresses = frappe.get_all(
            "Dynamic Link",
            filters={"link_name": customer, "link_doctype": "Customer"},
            fields=["parent"],
            pluck="parent"
        )
        
        if addresses:
            # Return first billing address
            for addr_name in addresses:
                addr = frappe.get_doc("Address", addr_name)
                if addr.address_type == "Billing":
                    return addr.name
            return addresses[0]
        
        # Create new address if none exists
        addr = frappe.get_doc({
            "doctype": "Address",
            "address_title": customer,
            "address_type": "Billing",
            "address_line1": cust.customer_name or "",
            "city": "Unknown",
            "country": "Mexico",
            "phone": cust.phone or "",
            "links": [{
                "link_doctype": "Customer",
                "link_name": customer
            }]
        })
        addr.insert()
        frappe.db.commit()
        return addr.name
        
    except Exception as e:
        print(f"❌ Error creating address: {e}")
        return None

# Test it
new_addr = create_address_from_customer(customer)
if new_addr:
    print(f"✅ Address ready: {new_addr}")
else:
    print(f"❌ Could not create/Find address")

# ============================================================
# SUMMARY
# ============================================================
print("\n" + "=" * 80)
print("DIAGNOSTIC COMPLETE")
print("=" * 80)

print("""
NEXT STEPS:
1. ✅ Cost Center fix - Should be working (check if applied)
2. ✅ Address fix - Can be tested with create_address_from_customer()
3. ⏳ Account fix - Waiting for parallel development (Server Script)

For parallel team:
- The Server Script should intercept Sales Invoice before_insert
- It should set doc.debit_to to the correct leaf account
- The account should be found in Party Account or computed via get_party_account()
""")

print("\n✅ Script completed successfully!")
