# Console Script for Investigating Account Issues
# Run with: bench console
# Then: exec(open('investigate_accounts.py').read())

import frappe

print("="*60)
print("ACCOUNT INVESTIGATION")
print("="*60)

# 1. Find the parent account that's causing issues
parent_account = "1105 - CLIENTES - AMB-W"

print(f"\n1. Checking parent account: {parent_account}")
account = frappe.get_doc("Account", parent_account)
print(f"   is_group: {account.is_group}")
print(f"   parent_account: {account.parent_account}")

# 2. Find all leaf (non-group) accounts under this parent
print(f"\n2. Finding leaf accounts under: {parent_account}")
leaf_accounts = frappe.get_all(
    "Account",
    filters={
        "parent_account": parent_account,
        "is_group": 0
    },
    fields=["name", "account_currency", "company"]
)

print(f"   Found {len(leaf_accounts)} leaf accounts:")
for acc in leaf_accounts:
    print(f"   - {acc.name} (Currency: {acc.account_currency}, Company: {acc.company})")

# 3. Try to find receivable accounts for AMB-Wellness company
print(f"\n3. Finding receivable accounts for AMB-Wellness")
receivable_accounts = frappe.get_all(
    "Account",
    filters={
        "company": "AMB-Wellness",
        "account_type": "Receivable",
        "is_group": 0
    },
    fields=["name", "account_currency"]
)

print(f"   Found {len(receivable_accounts)} receivable accounts:")
for acc in receivable_accounts[:10]:  # Show first 10
    print(f"   - {acc.name} (Currency: {acc.account_currency})")

# 4. Find all accounts under "1105 - CLIENTES" parent
print(f"\n4. Finding all accounts under '1105 - CLIENTES'")
all_clientes = frappe.get_all(
    "Account",
    filters={
        "parent_account": ["like", "%CLIENTES%"],
    },
    fields=["name", "is_group", "account_currency", "company"]
)

print(f"   Found {len(all_clientes)} accounts:")
for acc in all_clientes[:15]:  # Show first 15
    group_status = "GROUP" if acc.is_group else "LEAF"
    print(f"   - {acc.name} [{group_status}] (Currency: {acc.account_currency}, Company: {acc.company})")

# 5. Check what get_party_account returns
print(f"\n5. Testing get_party_account for LEGOSAN AB")
try:
    from erpnext.accounts.party import get_party_account
    party_account = get_party_account("Customer", "LEGOSAN AB", "AMB-Wellness")
    print(f"   Party account: {party_account}")
except Exception as e:
    print(f"   Error: {e}")

print("\n" + "="*60)
print("RECOMMENDATION:")
print("="*60)
print("""
To fix the issue, the auto-fix should:
1. Look for child accounts under '1105 - CLIENTES - AMB-W'
2. Find one that matches the currency (MXN or USD)
3. Set it as the debit_to account

Recommended leaf accounts to use:
- For MXN: 1105-01 - CLIENTES - AMB-W (or similar)
- For USD: Look for USD receivable account
""")
