"""
Batch Party Account Creator
===========================

Script para crear cuentas específicas de clientes (Party Accounts) de forma masiva.

Problema: 303 de 310 clientes (97.7%) usan cuenta genérica
Solución: Crear cuentas específicas basadas en tipo de cliente (Nacional/Extranjero)

Usage:
    # En bench console
    from raven_ai_agent.scripts.batch_party_account_creator import create_all_party_accounts
    result = create_all_party_accounts()

    # O con dry-run para ver qué se crearía
    result = create_all_party_accounts(dry_run=True)
"""

import frappe
from frappe import _
import re
from typing import Dict, List, Optional


def get_default_receivable_account(company: str = None) -> str:
    """Get default receivable account for company"""
    if not company:
        company = frappe.defaults.get_user_default("company") or "AMB Wellmart"
    
    return frappe.db.get_value("Company", company, "default_receivable_account")


def get_customer_type(customer: str) -> str:
    """Determine if customer is National or International based on customer group"""
    customer_group = frappe.db.get_value("Customer", customer, "customer_group")
    
    # Common patterns for international customers
    international_patterns = ['Export', 'Extranjero', 'International', 'Foreign', 'Overseas']
    
    for pattern in international_patterns:
        if pattern.lower() in customer_group.lower():
            return "Extranjero"
    
    return "Nacional"


def get_account_for_customer(customer: str, company: str = None) -> str:
    """
    Get the appropriate receivable account for a customer.
    
    Logic:
    - If customer has a specific Party Account, return it
    - Otherwise, use the default based on customer type:
      - Nacional: 1105.1.01 - CUENTAS POR COBRAR - NACIONALES
      - Extranjero: 1105.1.02 - CUENTAS POR COBRAR - EXTRANJEROS
    """
    if not company:
        company = frappe.defaults.get_user_default("company") or "AMB Wellmart"
    
    # Check if customer already has a Party Account
    existing_account = frappe.db.sql("""
        SELECT account FROM `tabParty Account`
        WHERE parent = %s
        AND parenttype = 'Customer'
        AND company = %s
        LIMIT 1
    """, (customer, company))
    
    if existing_account:
        return existing_account[0][0]
    
    # Determine customer type and assign appropriate account
    customer_type = get_customer_type(customer)
    
    if customer_type == "Extranjero":
        # Try to find the foreigner receivable account
        account = frappe.db.sql("""
            SELECT name FROM `tabAccount`
            WHERE company = %s
            AND account_type = 'Receivable'
            AND is_group = 0
            AND name LIKE '%EXTRANJEROS%'
            LIMIT 1
        """, company)
        
        if account:
            return account[0][0]
    
    # Fallback to default receivable account
    return get_default_receivable_account(company)


def create_party_account(customer: str, account: str, company: str = None) -> Dict:
    """
    Create a Party Account for a customer.
    
    Args:
        customer: Customer name
        account: Account to assign
        company: Company name
    
    Returns:
        Dict with success status and message
    """
    if not company:
        company = frappe.defaults.get_user_default("company") or "AMB Wellmart"
    
    try:
        # Check if already exists
        existing = frappe.db.sql("""
            SELECT name FROM `tabParty Account`
            WHERE parent = %s
            AND parenttype = 'Customer'
            AND company = %s
            AND account = %s
        """, (customer, company, account))
        
        if existing:
            return {
                "success": False,
                "message": f"Party Account already exists for {customer}"
            }
        
        # Create new Party Account
        pa = frappe.get_doc({
            "doctype": "Party Account",
            "parent": customer,
            "parenttype": "Customer",
            "parentfield": "accounts",
            "company": company,
            "account": account
        })
        
        # Insert via the customer document to trigger proper validation
        customer_doc = frappe.get_doc("Customer", customer)
        customer_doc.append("accounts", {
            "company": company,
            "account": account
        })
        customer_doc.save()
        
        return {
            "success": True,
            "message": f"Created Party Account for {customer}: {account}"
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"Error creating Party Account for {customer}: {str(e)}"
        }


def get_customers_without_party_account(company: str = None) -> List[Dict]:
    """
    Get all customers without a specific Party Account.
    
    Returns:
        List of customer dicts with name and customer_group
    """
    if not company:
        company = frappe.defaults.get_user_default("company") or "AMB Wellmart"
    
    customers = frappe.db.sql("""
        SELECT 
            c.name,
            c.customer_name,
            c.customer_group,
            c.customer_type,
            c.territory,
            c.disabled
        FROM `tabCustomer` c
        WHERE c.disabled = 0
        AND NOT EXISTS (
            SELECT 1 FROM `tabParty Account` pa
            WHERE pa.parent = c.name
            AND pa.parenttype = 'Customer'
            AND pa.company = %s
        )
        ORDER BY c.customer_name
    """, company, as_dict=True)
    
    return customers


def create_all_party_accounts(dry_run: bool = False, company: str = None) -> Dict:
    """
    Main function to create Party Accounts for all customers without one.
    
    Args:
        dry_run: If True, only show what would be created without making changes
        company: Company name (optional)
    
    Returns:
        Dict with results summary
    """
    if not company:
        company = frappe.defaults.get_user_default("company") or "AMB Wellmart"
    
    print("=" * 80)
    print("📋 BATCH PARTY ACCOUNT CREATOR")
    print("=" * 80)
    print(f"Company: {company}")
    print(f"Dry Run: {'Yes' if dry_run else 'No'}")
    print("=" * 80)
    
    # Get customers without Party Account
    customers = get_customers_without_party_account(company)
    
    if not customers:
        print("\n✅ All customers already have Party Accounts!")
        return {
            "success": True,
            "total_customers": 0,
            "created": 0,
            "skipped": 0,
            "errors": 0
        }
    
    print(f"\n📊 Found {len(customers)} customers without Party Accounts\n")
    
    results = {
        "success": True,
        "total_customers": len(customers),
        "created": 0,
        "skipped": 0,
        "errors": 0,
        "details": []
    }
    
    # Process each customer
    for idx, customer in enumerate(customers, 1):
        print(f"[{idx}/{len(customers)}] Processing: {customer.name} - {customer.customer_name}")
        
        # Get appropriate account
        account = get_account_for_customer(customer.name, company)
        
        if dry_run:
            print(f"  ⚡ Would create: {account}")
            results["created"] += 1
        else:
            # Create the Party Account
            result = create_party_account(customer.name, account, company)
            
            if result["success"]:
                print(f"  ✅ {result['message']}")
                results["created"] += 1
            else:
                print(f"  ⚠️ {result['message']}")
                results["skipped"] += 1
            
            results["details"].append({
                "customer": customer.name,
                "account": account,
                "result": result
            })
    
    # Summary
    print("\n" + "=" * 80)
    print("📋 SUMMARY")
    print("=" * 80)
    print(f"Total customers processed: {results['total_customers']}")
    print(f"Party Accounts created: {results['created']}")
    print(f"Skipped (already exists): {results['skipped']}")
    print(f"Errors: {results['errors']}")
    print("=" * 80)
    
    if not dry_run and results["created"] > 0:
        print(f"\n✅ Successfully created {results['created']} Party Accounts!")
        print("💡 Tip: Run Data Quality Scanner to verify the changes:")
        print("   @ai scan [customer_name]")
    
    return results


def create_party_accounts_for_customer_group(customer_group: str, company: str = None) -> Dict:
    """
    Create Party Accounts for all customers in a specific customer group.
    
    Args:
        customer_group: Customer group name
        company: Company name (optional)
    
    Returns:
        Dict with results
    """
    if not company:
        company = frappe.defaults.get_user_default("company") or "AMB Wellmart"
    
    customers = frappe.db.sql("""
        SELECT name FROM `tabCustomer`
        WHERE disabled = 0
        AND customer_group = %s
    """, customer_group, as_dict=True)
    
    print(f"Found {len(customers)} customers in group '{customer_group}'")
    
    results = {
        "success": True,
        "processed": 0,
        "created": 0
    }
    
    for customer in customers:
        account = get_account_for_customer(customer.name, company)
        result = create_party_account(customer.name, account, company)
        
        if result["success"]:
            results["created"] += 1
        
        results["processed"] += 1
    
    return results


def add_raven_command_support():
    """
    Add Raven AI command support for Party Account creation.
    
    This can be called from Raven to create Party Accounts on-demand.
    """
    print("""
╔══════════════════════════════════════════════════════════════════════════╗
║                    RAVEN AI - PARTY ACCOUNT COMMANDS                    ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  Available Commands:                                                    ║
║                                                                          ║
║  @ai create party accounts                     - Create all missing     ║
║                                                Party Accounts           ║
║                                                                          ║
║  @ai create party accounts dry-run            - Preview what would    ║
║                                                be created              ║
║                                                                          ║
║  @ai create party accounts for [group]        - Create accounts for  ║
║                                                specific group          ║
║                                                                          ║
║  @ai check party accounts                     - Show status of       ║
║                                                Party Accounts          ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝
    """)


# Entry point for bench console
if __name__ == "__main__":
    # Run with dry-run first
    print("Running in dry-run mode to preview changes...\n")
    result = create_all_party_accounts(dry_run=True)
    
    print("\n" + "=" * 80)
    print("To execute the changes, run:")
    print("create_all_party_accounts(dry_run=False)")
    print("=" * 80)
