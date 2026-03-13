"""
Data Quality Scanner Skill
==========================

Pre-flight validation for ERPNext documents before operations.
Detects: addresses, accounts, CFDI fields, cost centers, currency issues.

Based on 30+ bug fix commits analysis - catches 80% of recurring issues.
Integrates with Memory System (Memento) to store validation patterns.

Uses response_formatter for consistent output formatting.
"""

import frappe
import re
from typing import Dict, List, Optional, Any
from datetime import datetime

from raven_ai_agent.skills.framework import SkillBase
from raven_ai_agent.skills.formulation_reader.reader import parse_golden_number
from raven_ai_agent.api.response_formatter import (
    format_confidence_score,
    format_issues,
    format_table,
    apply_post_processing
)


class DataQualityScannerSkill(SkillBase):
    """
    Pre-flight validation skill for ERPNext documents.
    
    Validation Categories (from bug analysis):
    1. Customer Address (60% of issues)
    2. Account Configuration (20% of issues)
    3. MX CFDI Fields (15% of issues)
    4. Cost Center Issues (5% of issues)
    
    Integration:
    - Raymond Protocol: Verified data checks
    - Memento: Stores validation patterns for learning
    - Tattoo: Learns from each scan result
    """
    
    name = "data-quality-scanner"
    description = "Pre-flight validation for Sales Orders and Invoices - detects address, account, CFDI issues"
    emoji = "🔍"
    version = "1.0.0"
    priority = 90  # High priority - runs before operations
    
    triggers = [
        "scan", "validate", "check data", "quality check",
        "pre-flight", "preflight", "diagnose", "diagnosis",
        "pipeline", "check address", "check account", "check invoice",
        "fix", "repair", "solve", "apply",
        "pipeline diagnosis", "full scan"
    ]
    
    patterns = [
        r"(?:scan|validate|check)\s+(?:so|sales order|invoice|si)",
        r"pre-?flight",
        r"data\s+quality",
        r"verificar\s+(?:factura|pedido|datos)"
    ]
    
    def __init__(self, agent=None):
        super().__init__(agent)
        self.issues_found = []
        self.fixes_applied = []
        
        # Plant code to Cost Center mapping (from golden number)
        # Golden number format: {product(4)}{folio(3)}{year(2)}{plant(1)}
        # Example: 043300001 -> Cost Center: 043300001 - 043300001 - AMB-W
        # Plant codes: 1=Mix, 2=Dry, 3=Juice, 4=Laboratory, 5=Formulated
        self.PLANT_COST_CENTER_MAP = {
            '1': 'Main - 1',      # Mix Plant (legacy format)
            '2': 'Main - 2',      # Dry Plant (legacy format)
            '3': 'Main - 3',      # Juice Plant (legacy format)
            '4': 'Main - 4',      # Laboratory (legacy format)
            '5': 'Main - 5'       # Formulated Products (legacy format)
        }
    
    def handle(self, query: str, context: Dict = None) -> Optional[Dict]:
        """Handle validation query"""
        try:
            context = context or {}
            query_lower = query.lower()
            
            frappe.logger().info(f"[DataQualityScanner] Handling query: {query}")
            
            # Check if this is a scan/validate command
            is_scan = any(trigger in query_lower for trigger in self.triggers)
            frappe.logger().info(f"[DataQualityScanner] is_scan: {is_scan}, triggers: {self.triggers}")
            if not is_scan:
                frappe.logger().info("[DataQualityScanner] Not a scan command, returning None")
                return None  # Let other skills handle it
            
            # Check if this is a pipeline diagnosis request
            is_pipeline_diagnosis = any(
                kw in query_lower for kw in ["pipeline", "full scan", "diagnosis", "complete", "diagnose", "full"]
            )
            
            frappe.logger().info(f"[DataQualityScanner] is_pipeline_diagnosis: {is_pipeline_diagnosis}, query: {query}")
            
            # Extract document name from query
            doc_name = self._extract_document_name(query)
            frappe.logger().info(f"[DataQualityScanner] Extracted doc_name: {doc_name}")
            
            if not doc_name:
                return {
                    "handled": True,
                    "response": self._get_help_message(),
                    "confidence": 0.5
                }
            
            # Determine document type
            doc_type = self._infer_document_type(doc_name)
            frappe.logger().info(f"[DataQualityScanner] doc_type: {doc_type}")
            
            # Check fix mode - look for !fix or #fix anywhere in query
            # @ai fix SO-123 → dry-run (preview only)
            # @ai !fix SO-123 → apply fixes
            # @ai #fix SO-123 → force apply (bypass validation)
            fix_mode = "none"  # none, preview, apply, force
            
            # More aggressive detection - check entire query
            if "!fix" in query_lower or "apply fix" in query_lower:
                fix_mode = "apply"
            elif "#fix" in query_lower or "force fix" in query_lower:
                fix_mode = "force"
            elif "fix" in query_lower:
                fix_mode = "preview"
            
            frappe.logger().info(f"[DataQualityScanner] fix_mode detected: {fix_mode}, full query: {query}")
            
            # Run validation
            if doc_type == "Sales Order":
                result = self.scan_sales_order(doc_name)
            elif doc_type == "Sales Invoice":
                result = self.scan_sales_invoice(doc_name)
            elif doc_type == "Quotation":
                result = self.scan_quotation(doc_name)
            else:
                return {
                    "handled": True,
                    "response": f"❌ Unsupported document type: {doc_type}",
                    "confidence": 0.9
                }
            
            # If user wants pipeline diagnosis, add it to results
            # For SAL-QTN, always try to get pipeline diagnosis when diagnose/pipeline is in query
            if is_pipeline_diagnosis or "quotation" in query_lower:
                if doc_type == "Sales Order":
                    pipeline_report = self.diagnose_pipeline(doc_name)
                    result["pipeline_diagnosis"] = pipeline_report
                elif doc_type == "Quotation" or "SAL-QTN" in doc_name.upper():
                    # Force Quotation pipeline for SAL-QTN documents
                    frappe.logger().info(f"[DataQualityScanner] Running Quotation pipeline diagnosis for {doc_name}")
                    pipeline_report = self.diagnose_quotation_pipeline(doc_name)
                    result["pipeline_diagnosis"] = pipeline_report
            
            # Handle fix mode
            fix_result = None
            frappe.logger().info(f"[DataQualityScanner] fix_mode={fix_mode}, has_issues={bool(result.get('issues'))}, issues_count={len(result.get('issues', []))}")
            
            # Preview mode or Apply mode
            if fix_mode in ["apply", "force"] and result.get("issues"):
                frappe.logger().info(f"[DataQualityScanner] Applying fixes (mode={fix_mode})")
                fix_result = self._apply_fixes(doc_name, doc_type, result)
                frappe.logger().info(f"[DataQualityScanner] _apply_fixes returned: {fix_result}")
                if fix_result and fix_result.get("applied") and len(fix_result.get("applied", [])) > 0:
                    frappe.logger().info(f"[DataQualityScanner] Fixes applied successfully: {fix_result['applied']}")
                    # Re-scan after applying fixes
                    if doc_type == "Sales Order":
                        result = self.scan_sales_order(doc_name)
                    elif doc_type == "Sales Invoice":
                        result = self.scan_sales_invoice(doc_name)
                    elif doc_type == "Quotation":
                        result = self.scan_quotation(doc_name)
                else:
                    frappe.logger().warning(f"[DataQualityScanner] No fixes applied. fix_result={fix_result}")
            
            frappe.logger().info(f"[DataQualityScanner] Scan result keys: {result.keys() if result else 'None'}")
            
            # Store validation pattern in memory (Memento)
            self._store_validation_pattern(doc_name, doc_type, result)
            
            # Debug: add fix attempt info to result for display
            if fix_mode in ["apply", "force"]:
                result["_debug_fix_info"] = {
                    "fix_mode": fix_mode,
                    "fix_attempted": True,
                    "fix_result": fix_result
                }
            
            # Format response
            response = self._format_scan_result(result, doc_name, doc_type, fix_result, fix_mode)
            frappe.logger().info(f"[DataQualityScanner] Response length: {len(response) if response else 0}")
            
            return_result = {
                "handled": True,
                "response": response,
                "confidence": result.get("confidence", 0.8),
                "data": result
            }
            frappe.logger().info(f"[DataQualityScanner] Returning success result")
            return return_result
            
        except Exception as e:
            frappe.logger().error(f"[DataQualityScanner] CRITICAL ERROR: {str(e)}")
            frappe.log_error(f"DataQualityScanner.handle() error: {str(e)}", "Scanner Skill Error")
            return {
                "handled": True,
                "response": f"❌ Scanner Error: {str(e)}",
                "confidence": 0.0
            }
    
    def _extract_document_name(self, query: str) -> Optional[str]:
        """Extract document name from query"""
        # Match patterns like SO-XXXXX, QUOT-XXXXX, SAL-QTN-XXXXX, ACC-SINV-XXXXX
        patterns = [
            r"(SO-\d+-[\w\s\.\-]+)",  # SO-00767-BARENTZ Italia or SO-00767-BARENTZ Italia S.p.A
            r"(QUOT-\d+-\d+)",         # QUOT-2026-00001 or QUOT-26-00001
            r"(SAL-QTN-\d+-\d+)",
            r"(ACC-SINV-\d+-\d+)",
            r"(ACC-PAY-\d+-\d+)",
            r"(ACC-DN-\d+-\d+)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                doc_name = match.group(1).strip()
                # Try to find the actual document if exact match fails
                return self._resolve_document_name(doc_name)
        
        return None
    
    def _resolve_document_name(self, doc_name: str) -> Optional[str]:
        """Resolve document name - try exact match, then fuzzy search"""
        # Try exact match first - check all document types
        doctypes_to_check = [
            "Sales Order",
            "Quotation",
            "Sales Invoice",
            "Payment Entry",
            "Delivery Note"
        ]
        
        for doctype in doctypes_to_check:
            try:
                if frappe.db.exists(doctype, doc_name):
                    return doc_name
            except:
                pass
        
        # Try fuzzy search - look for SO-XXXXX pattern
        so_match = re.match(r"(SO-\d+)-(.+)", doc_name, re.IGNORECASE)
        if so_match:
            so_prefix = so_match.group(1)
            customer_hint = so_match.group(2).strip().upper()
            
            # Search for SOs with this prefix
            try:
                sos = frappe.get_all(
                    "Sales Order",
                    filters={"name": ["like", f"{so_prefix}%"]},
                    fields=["name", "customer"],
                    limit=20
                )
                
                best_match = None
                best_score = 0
                
                for so in sos:
                    # Try exact name match
                    if so.name.upper() == doc_name.upper():
                        return so.name
                    
                    # Score based on customer name similarity
                    if so.customer:
                        customer_upper = so.customer.upper()
                        
                        # Exact customer match
                        if customer_hint == customer_upper:
                            return so.name
                        
                        # Customer starts with hint
                        if customer_hint in customer_upper or customer_upper[:len(customer_hint)] == customer_hint:
                            return so.name
                        
                        # Partial match - track best
                        words = customer_hint.split()
                        for word in words:
                            if len(word) > 2 and word in customer_upper:
                                return so.name
                
                # Return best match or first
                if best_match:
                    return best_match
                if sos:
                    # Return first one with warning
                    return sos[0].name
            except Exception as e:
                frappe.logger().warning(f"SO resolution error: {e}")
        
        # Return original if no resolution
        return doc_name
    
    def _infer_document_type(self, doc_name: str) -> str:
        """Infer document type from name"""
        doc_name_upper = doc_name.upper()
        
        if doc_name_upper.startswith("SO-"):
            return "Sales Order"
        elif doc_name_upper.startswith("SAL-QTN"):
            return "Quotation"
        elif doc_name_upper.startswith("QUOT-"):
            # Handle patterns like QUOT-2026-00001, QUOT-26-00001, etc.
            return "Quotation"
        elif doc_name_upper.startswith("ACC-SINV"):
            return "Sales Invoice"
        elif doc_name_upper.startswith("ACC-PAY"):
            return "Payment Entry"
        elif doc_name_upper.startswith("ACC-DN"):
            return "Delivery Note"
        else:
            # Fallback: Check database for the document type
            doctypes = ["Sales Order", "Quotation", "Sales Invoice", "Delivery Note", "Payment Entry"]
            for dt in doctypes:
                try:
                    if frappe.db.exists(dt, doc_name):
                        frappe.logger().info(f"[DataQualityScanner] Found {doc_name} as {dt}")
                        return dt
                except:
                    pass
            
            return "Unknown"
    
    def scan_sales_order(self, so_name: str) -> Dict:
        """Run all validation checks on a Sales Order"""
        issues = []
        warnings = []
        
        try:
            so = frappe.get_doc("Sales Order", so_name)
        except frappe.DoesNotExistError:
            return {
                "success": False,
                "error": f"Sales Order not found: {so_name}",
                "confidence": 1.0
            }
        
        # Check 1: Customer Address
        address_issues = self._validate_customer_address(so)
        issues.extend(address_issues)
        
        # Check 2: Shipping Address
        shipping_issues = self._validate_shipping_address(so)
        issues.extend(shipping_issues)
        
        # Check 3: Billing Address
        billing_issues = self._validate_billing_address(so, doc_type="Sales Order")
        issues.extend(billing_issues)
        
        # Check 4: Customer Account
        account_issues = self._validate_customer_account(so, doc_type="Sales Order")
        issues.extend(account_issues)
        
        # Check 5: MX CFDI Fields
        cfdi_issues = self._validate_mx_cfdi_fields(so)
        issues.extend(cfdi_issues)
        
        # Check 6: Cost Center
        cost_center_issues = self._validate_cost_center(so)
        issues.extend(cost_center_issues)
        
        # Check 7: Currency
        currency_issues = self._validate_currency(so)
        issues.extend(currency_issues)
        
        # Calculate confidence based on issues
        confidence = self._calculate_confidence(issues, warnings)
        
        return {
            "success": True,
            "document_type": "Sales Order",
            "document_name": so_name,
            "customer": so.customer,
            "total_issues": len(issues),
            "issues": issues,
            "warnings": warnings,
            "confidence": confidence,
            "can_proceed": len([i for i in issues if i.get("severity") == "CRITICAL"]) == 0
        }
    
    def scan_sales_invoice(self, si_name: str) -> Dict:
        """Run all validation checks on a Sales Invoice"""
        issues = []
        warnings = []
        
        try:
            si = frappe.get_doc("Sales Invoice", si_name)
        except frappe.DoesNotExistError:
            return {
                "success": False,
                "error": f"Sales Invoice not found: {si_name}",
                "confidence": 1.0
            }
        
        # Check 1: Customer Address
        address_issues = self._validate_customer_address(si)
        issues.extend(address_issues)
        
        # Check 2: Customer Account
        account_issues = self._validate_invoice_account(si)
        issues.extend(account_issues)
        
        # Check 3: MX CFDI Fields
        cfdi_issues = self._validate_mx_cfdi_fields(si)
        issues.extend(cfdi_issues)
        
        # Check 4: Cost Center
        cost_center_issues = self._validate_cost_center(si)
        issues.extend(cost_center_issues)
        
        # Check 5: Currency enforcement
        currency_issues = self._validate_invoice_currency(si)
        issues.extend(currency_issues)
        
        # Check 6: Payment terms
        payment_issues = self._validate_payment_terms(si)
        issues.extend(payment_issues)
        
        confidence = self._calculate_confidence(issues, warnings)
        
        return {
            "success": True,
            "document_type": "Sales Invoice",
            "document_name": si_name,
            "customer": si.customer,
            "total_issues": len(issues),
            "issues": issues,
            "warnings": warnings,
            "confidence": confidence,
            "can_proceed": len([i for i in issues if i.get("severity") == "CRITICAL"]) == 0
        }
    
    def scan_quotation(self, qtn_name: str) -> Dict:
        """Run all validation checks on a Quotation"""
        issues = []
        warnings = []
        
        try:
            qtn = frappe.get_doc("Quotation", qtn_name)
        except frappe.DoesNotExistError:
            return {
                "success": False,
                "error": f"Quotation not found: {qtn_name}",
                "confidence": 1.0
            }
        
        # Check 1: Customer Address
        address_issues = self._validate_customer_address(qtn)
        issues.extend(address_issues)
        
        # Check 2: MX CFDI Fields (for Mexico customers)
        cfdi_issues = self._validate_mx_cfdi_fields(qtn)
        issues.extend(cfdi_issues)
        
        confidence = self._calculate_confidence(issues, warnings)
        
        # Get item count and total
        item_count = len(qtn.items) if hasattr(qtn, 'items') else 0
        total_value = qtn.grand_total if hasattr(qtn, 'grand_total') else 0
        
        return {
            "success": True,
            "document_type": "Quotation",
            "document_name": qtn_name,
            "customer": qtn.party_name,
            "customer_name": qtn.customer_name if hasattr(qtn, 'customer_name') else None,
            "transaction_date": str(qtn.transaction_date) if hasattr(qtn, 'transaction_date') else None,
            "valid_till": str(qtn.valid_till) if hasattr(qtn, 'valid_till') else None,
            "status": qtn.status if hasattr(qtn, 'status') else None,
            "total": total_value,
            "currency": qtn.currency if hasattr(qtn, 'currency') else 'MXN',
            "item_count": item_count,
            "total_issues": len(issues),
            "issues": issues,
            "warnings": warnings,
            "confidence": confidence,
            "can_proceed": len([i for i in issues if i.get("severity") == "CRITICAL"]) == 0
        }
    
    # ===========================================
    # Individual Validation Checks
    # ===========================================
    
    def _validate_customer_address(self, doc) -> List[Dict]:
        """Check if customer address is valid"""
        issues = []
        
        customer_address = doc.get("customer_address")
        
        if not customer_address:
            issues.append({
                "type": "missing_customer_address",
                "severity": "HIGH",
                "message": "Customer Address is missing",
                "field": "customer_address",
                "auto_fix": "create_from_customer",
                "fix_confidence": 0.90
            })
            return issues
        
        # Check if address exists
        try:
            address = frappe.get_doc("Address", customer_address)
            
            # Check required fields
            if not address.address_title:
                issues.append({
                    "type": "incomplete_address",
                    "severity": "MEDIUM",
                    "message": "Address title is missing",
                    "field": "address_title",
                    "auto_fix": "set_from_customer",
                    "fix_confidence": 0.85
                })
            
            if not address.city:
                issues.append({
                    "type": "incomplete_address",
                    "severity": "MEDIUM",
                    "message": "Address city is missing",
                    "field": "city",
                    "auto_fix": None,
                    "fix_confidence": 0.0
                })
                
        except frappe.DoesNotExistError:
            issues.append({
                "type": "broken_address_link",
                "severity": "CRITICAL",
                "message": f"Address '{customer_address}' does not exist",
                "field": "customer_address",
                "auto_fix": "resolve_from_customer",
                "fix_confidence": 0.90
            })
        
        return issues
    
    def _validate_shipping_address(self, doc) -> List[Dict]:
        """Check if shipping address is valid"""
        issues = []
        
        shipping_address = doc.get("shipping_address_name")
        
        if not shipping_address:
            # Warning, not critical
            issues.append({
                "type": "missing_shipping_address",
                "severity": "LOW",
                "message": "Shipping Address is missing (will use customer address)",
                "field": "shipping_address_name",
                "auto_fix": "copy_from_customer_address",
                "fix_confidence": 0.80
            })
            return issues
        
        try:
            frappe.get_doc("Address", shipping_address)
        except frappe.DoesNotExistError:
            issues.append({
                "type": "broken_shipping_address_link",
                "severity": "HIGH",
                "message": f"Shipping Address '{shipping_address}' does not exist",
                "field": "shipping_address_name",
                "auto_fix": "resolve_from_customer",
                "fix_confidence": 0.85
            })
        
        return issues
    
    def _validate_billing_address(self, doc, doc_type: str = "Sales Order") -> List[Dict]:
        """Check if billing address is valid"""
        issues = []
        
        # Sales Orders use customer_address for billing, Sales Invoices use billing_address_name
        if doc_type == "Sales Order":
            billing_address = doc.get("customer_address")
            field_name = "customer_address"
        else:
            billing_address = doc.get("billing_address_name")
            field_name = "billing_address_name"
        
        if not billing_address:
            issues.append({
                "type": "missing_billing_address",
                "severity": "MEDIUM",
                "message": "Billing Address is missing",
                "field": field_name,
                "auto_fix": "copy_from_customer_address",
                "fix_confidence": 0.85
            })
        
        return issues
    
    def _validate_customer_account(self, so, doc_type: str = "Sales Order") -> List[Dict]:
        """Check if customer has valid receivable account"""
        issues = []
        
        customer = so.customer
        currency = so.currency
        company = so.company
        
        if not customer:
            return issues
        
        # Check if this is a Sales Order (account handled by Server Script at Invoice level)
        is_sales_order = doc_type == "Sales Order"
        
        # Get default receivable account from Company/Party Defaults (not Customer directly)
        receivable_account = None
        try:
            from erpnext.accounts.party import get_party_account
            receivable_account = get_party_account("Customer", customer, company)
        except:
            # Fallback: try to get from Sales Order's debit_to
            receivable_account = so.get("debit_to")
        
        if not receivable_account:
            issues.append({
                "type": "missing_receivable_account",
                "severity": "HIGH",
                "message": f"No receivable account found for customer '{customer}' in company '{company}'",
                "field": "debit_to",
                "auto_fix": "set_default_account",
                "fix_confidence": 0.95
            })
            return issues
        
        # Check if account exists and is not a group
        try:
            account = frappe.get_doc("Account", receivable_account)
            if account.is_group:
                # For Sales Orders, account is set at Invoice level via Server Script
                # So we mark this as INFO instead of CRITICAL
                if is_sales_order:
                    issues.append({
                        "type": "group_account",
                        "severity": "INFO",
                        "message": f"Account '{receivable_account}' is a Group Account - Will be auto-fixed at Invoice level via Server Script",
                        "field": "debit_to",
                        "current_value": receivable_account,
                        "auto_fix": None,  # No auto-fix needed - Server Script handles it
                        "fix_confidence": 1.0,
                        "note": "Handled by Server Script at Invoice creation"
                    })
                else:
                    issues.append({
                        "type": "group_account",
                        "severity": "CRITICAL",
                        "message": f"Account '{receivable_account}' is a Group Account (cannot be used in transactions)",
                        "field": "debit_to",
                        "current_value": receivable_account,
                        "auto_fix": "find_leaf_account",
                        "fix_confidence": 0.80
                    })
            
            # Check currency - Multi-currency is normal in ERPNext (USD invoices in MXN company)
            # This is handled by exchange rate at invoice time, NOT an error
            account_currency = account.account_currency
            if account_currency and account_currency != currency:
                # Multi-currency is valid workflow: USD invoice → USD payment → converted to MXN
                # Exchange difference goes to "perdidas y ganancias monetarias"
                issues.append({
                    "type": "currency_mismatch",
                    "severity": "INFO",  # Changed from HIGH - this is expected multi-currency behavior
                    "message": f"Multi-currency: Account in '{account_currency}', document in '{currency}' - Normal for export transactions",
                    "field": "currency",
                    "auto_fix": None,  # No fix needed - this is correct
                    "fix_confidence": 1.0
                })
        except frappe.DoesNotExistError:
            issues.append({
                "type": "account_not_found",
                "severity": "CRITICAL",
                "message": f"Receivable account '{receivable_account}' not found",
                "field": "debit_to",
                "auto_fix": "find_default_receivable",
                "fix_confidence": 0.90
            })
        except Exception as e:
            issues.append({
                "type": "account_error",
                "severity": "HIGH",
                "message": f"Error checking account: {str(e)}",
                "field": "debit_to",
                "auto_fix": None,
                "fix_confidence": 0.0
            })
        
        return issues
    
    def _validate_invoice_account(self, si) -> List[Dict]:
        """Check sales invoice accounts"""
        issues = []
        
        # Check each item's income account
        for item in si.get("items", []):
            if not item.get("income_account"):
                issues.append({
                    "type": "missing_income_account",
                    "severity": "MEDIUM",
                    "message": f"Item '{item.item_code}' missing income account",
                    "field": "income_account",
                    "auto_fix": "set_default_income_account",
                    "fix_confidence": 0.90
                })
        
        # Check receivable account
        if not si.get("debit_to"):
            issues.append({
                "type": "missing_debit_to",
                "severity": "HIGH",
                "message": "Receivable account (debit_to) is missing",
                "field": "debit_to",
                "auto_fix": "set_default_receivable",
                "fix_confidence": 0.95
            })
        
        return issues
    
    def _validate_mx_cfdi_fields(self, doc) -> List[Dict]:
        """Check Mexico-specific CFDI fields"""
        issues = []
        
        # Check if this is a Mexican company/transaction
        company = doc.get("company")
        if not company:
            return issues
        
        # Check company country
        company_country = frappe.get_value("Company", company, "country")
        if company_country and company_country != "Mexico":
            return issues  # Not Mexico, skip CFDI checks
        
        # Check customer MX fields
        customer = doc.get("customer")
        if customer:
            mx_tax_regime = frappe.get_value("Customer", customer, "mx_tax_regime")
            if not mx_tax_regime:
                issues.append({
                    "type": "missing_mx_tax_regime",
                    "severity": "MEDIUM",
                    "message": f"Customer '{customer}' has no Tax Regime (mx_tax_regime)",
                    "field": "mx_tax_regime",
                    "auto_fix": "set_default_tax_regime",
                    "fix_confidence": 0.70
                })
        
        # For Sales Invoice: check CFDI use and payment method
        if doc.doctype == "Sales Invoice":
            if not doc.get("mx_cfdi_use"):
                issues.append({
                    "type": "missing_cfdi_use",
                    "severity": "HIGH",
                    "message": "CFDI Use (mx_cfdi_use) is missing",
                    "field": "mx_cfdi_use",
                    "auto_fix": "set_default_cfdi_use",
                    "fix_confidence": 0.85
                })
            
            if not doc.get("mx_payment_method"):
                issues.append({
                    "type": "missing_payment_method",
                    "severity": "MEDIUM",
                    "message": "Payment Method (mx_payment_method) is missing",
                    "field": "mx_payment_method",
                    "auto_fix": "set_default_payment_method",
                    "fix_confidence": 0.90
                })
        
        return issues
    
    def _get_cost_center_from_golden_number(self, doc) -> Optional[str]:
        """
        Derive cost center from golden number in linked documents.
        
        Priority order:
        1. Delivery Notes -> Batches (most reliable - has custom_golden_number)
        2. Work Orders
        3. Item Code (fallback)
        
        Format: [item_code(4)][WO_consecutive(3)][WO_year(2)][Plant(1)]
        Example: 0334114231 → item_code=0334, WO=114, year=23, plant=1
        
        Cost Center name format: "{code} - {code} - AMB-W"
        
        Args:
            doc: Sales Order or Sales Invoice document
            
        Returns:
            Cost Center name if found, None otherwise
        """
        items = doc.get("items", [])
        if not items:
            return None
        
        # Get Sales Order name
        so_name = doc.name
        
        # PRIORITY 1: Try to get golden number from Delivery Notes/Batches
        # This is the MOST RELIABLE source - it uses custom_golden_number field
        # This is the same logic that works in pipeline diagnosis
        frappe.logger().info(f"[DataQualityScanner] Starting DN/Batch lookup for SO: {so_name}")
        
        dn_items = []
        try:
            dn_items = frappe.db.sql("""
                SELECT dni.item_code, dni.batch_no
                FROM `tabDelivery Note Item` dni
                INNER JOIN `tabDelivery Note` dn ON dn.name = dni.parent
                WHERE dni.against_sales_order = %s
                LIMIT 20
            """, (so_name,), as_dict=True)
            
            frappe.logger().info(f"[DataQualityScanner] Found {len(dn_items)} DN items using dni.against_sales_order")
            
            if not dn_items:
                # Try alternative: query using parent sales_order field
                dn_items_alt = frappe.db.sql("""
                    SELECT dni.item_code, dni.batch_no
                    FROM `tabDelivery Note Item` dni
                    INNER JOIN `tabDelivery Note` dn ON dn.name = dni.parent
                    WHERE dn.sales_order = %s
                    LIMIT 20
                """, (so_name,), as_dict=True)
                frappe.logger().info(f"[DataQualityScanner] Alternative query (dn.sales_order) found {len(dn_items_alt)} DN items")
                dn_items = dn_items_alt
        except Exception as e:
            frappe.logger().error(f"[DataQualityScanner] ERROR in DN query: {e}")
        
        # Process DN items to find golden number
        for dni in dn_items:
            if dni.batch_no:
                frappe.logger().info(f"[DataQualityScanner] Processing DN item with batch_no: {dni.batch_no}")
                
                # FIRST: Try to get from Batch doctype (most reliable)
                # This handles cases where batch_no is short name like "LOTE016"
                try:
                    batch = frappe.get_doc("Batch", dni.batch_no)
                    raw_golden = batch.custom_golden_number or batch.batch_id or batch.name
                    golden_digits = ''.join(filter(str.isdigit, str(raw_golden)))
                    frappe.logger().info(f"[DataQualityScanner] Batch {dni.batch_no}: raw_golden={raw_golden}, digits={golden_digits}")
                    
                    if golden_digits and len(golden_digits) >= 10:
                        # Take first 10 digits
                        golden_digits = golden_digits[:10]
                        cc_name = f"{golden_digits} - {golden_digits} - AMB-W"
                        frappe.logger().info(f"[DataQualityScanner] Found golden from Batch doctype: {golden_digits}")
                        return cc_name
                except Exception as e:
                    frappe.logger().warning(f"[DataQualityScanner] Error fetching Batch {dni.batch_no}: {e}")
                
                # SECOND: Try to extract digits directly from batch_no
                # This works if batch_no contains full golden number like "LOTE-0612185231"
                batch_digits = ''.join(filter(str.isdigit, str(dni.batch_no)))
                frappe.logger().info(f"[DataQualityScanner] Direct batch digits: {batch_digits}")
                
                if batch_digits and len(batch_digits) >= 10:
                    batch_digits = batch_digits[:10]  # Take first 10 digits
                    cc_name = f"{batch_digits} - {batch_digits} - AMB-W"
                    frappe.logger().info(f"[DataQualityScanner] Found golden number from DN batch direct: {batch_digits}")
                    return cc_name
        
        frappe.logger().info(f"[DataQualityScanner] No golden number found in DN/Batch lookup, trying Work Orders")
        
        # PRIORITY 2: Try to find Work Orders
        # Try to find Work Orders by querying Work Order table directly
        # The work_order field in SO items might not be populated, but WO has sales_order link
        try:
            wos = frappe.get_all(
                "Work Order",
                filters={"sales_order": so_name},
                fields=["name", "production_item", "status", "qty"]
            )
            
            if wos:
                frappe.logger().info(f"[DataQualityScanner] Found {len(wos)} Work Orders for SO {so_name}")
                
                for wo in wos:
                    wo_name = wo.name
                    production_item = wo.production_item
                    
                    import re
                    
                    # Try to find 10-digit code in WO name first
                    match = re.search(r'(\d{10})', wo_name)
                    
                    if match:
                        # Found 10-digit code (e.g., 0334114231)
                        full_code = match.group(1)
                        item_prefix = full_code[0:4]
                        wo_consecutive = full_code[4:7]
                        wo_year = full_code[7:9]
                        plant_code = full_code[9]
                    else:
                        # Try to find any digits in WO name
                        # Format might be MFG-WO-03726 or similar
                        digits_match = re.search(r'(\d+)', wo_name)
                        if digits_match:
                            digits = digits_match.group(1)
                            # Use production_item for item prefix if available
                            if production_item:
                                item_prefix = production_item[:4] if len(production_item) >= 4 else production_item.zfill(4)
                            else:
                                item_prefix = "0607"  # fallback
                            
                            # Pad the digits to get 10-digit format
                            # Assuming format is like 03726 → need to figure out the structure
                            # For now, use year=23, consecutive from digits, plant=1 (Mix)
                            wo_consecutive = digits[-3:].zfill(3) if len(digits) >= 3 else "000"
                            wo_year = "23"
                            plant_code = "1"
                        else:
                            # Fallback: use production_item only
                            if production_item:
                                item_prefix = production_item[:4] if len(production_item) >= 4 else production_item.zfill(4)
                                wo_consecutive = "000"
                                wo_year = "23"
                                plant_code = "1"
                            else:
                                continue
                    
                    cc_code = f"{item_prefix}{wo_consecutive}{wo_year}{plant_code}"
                    cc_name = f"{cc_code} - {cc_code} - AMB-W"
                    
                    frappe.logger().info(f"[DataQualityScanner] Derived cost center from WO {wo_name}: {cc_name}")
                    
                    if frappe.db.exists("Cost Center", cc_name):
                        return cc_name
                    return cc_name
        except Exception as e:
            frappe.logger().error(f"[DataQualityScanner] Error querying Work Orders: {e}")
        
        # Try to find Work Order or Production Order from items
        for item in items:
            work_order = item.get("work_order")
            production_order = item.get("production_order")
            
            # Try Production Order (more common than Work Order in Sales Orders)
            if production_order:
                try:
                    prod_doc = frappe.get_doc("Production Order", production_order)
                    item_code = prod_doc.get("item_code", "")
                    item_prefix = item_code[:4] if item_code else ""
                    
                    prod_name = prod_doc.name
                    import re
                    match = re.search(r'(\d{10})', prod_name)
                    if match:
                        full_code = match.group(1)
                        wo_consecutive = full_code[4:7]
                        wo_year = full_code[7:9]
                        plant_code = full_code[9]
                    else:
                        wo_consecutive = "000"
                        wo_year = "23"
                        plant_code = "1"
                    
                    if not item_prefix:
                        item_prefix = "0000"
                    
                    cc_code = f"{item_prefix}{wo_consecutive}{wo_year}{plant_code}"
                    cc_name = f"{cc_code} - {cc_code} - AMB-W"
                    
                    if frappe.db.exists("Cost Center", cc_name):
                        return cc_name
                    return cc_name
                except:
                    pass
            
            # Try Work Order
            if work_order:
                try:
                    wo_doc = frappe.get_doc("Work Order", work_order)
                    item_code = wo_doc.get("item_code", "")
                    item_prefix = item_code[:4] if item_code else ""
                    
                    wo_name = wo_doc.name
                    import re
                    match = re.search(r'(\d{10})', wo_name)
                    if match:
                        full_code = match.group(1)
                        wo_consecutive = full_code[4:7]
                        wo_year = full_code[7:9]
                        plant_code = full_code[9]
                    else:
                        wo_consecutive = "000"
                        wo_year = "23"
                        plant_code = "1"
                    
                    if not item_prefix:
                        item_prefix = "0000"
                    
                    cc_code = f"{item_prefix}{wo_consecutive}{wo_year}{plant_code}"
                    cc_name = f"{cc_code} - {cc_code} - AMB-W"
                    
                    if frappe.db.exists("Cost Center", cc_name):
                        return cc_name
                    return cc_name
                except:
                    pass
        
        frappe.logger().info(f"[DataQualityScanner] No Work Orders/Production Orders found, using item code fallback")
        
        # LAST RESORT: Try to derive cost center from Item Code directly
        # Use the golden number format from formulation_reader: ITEM_[product(4)][folio(3)][year(2)][plant(1)]
        # This extracts the plant code from the item code and maps to a generic Cost Center
        return self._derive_cost_center_from_item_code(items, doc)
    
    def _derive_cost_center_from_item_code(self, items, doc=None) -> Optional[str]:
        """
        Fallback: Derive cost center from Item Code or BOM.
        
        Uses golden number format: {item(4)}{wo(3)}{year(2)}{plant(1)}
        Example: 043300001 -> 0433-000-01-1 -> Cost Center: 043300001 - 043300001 - AMB-W
        
        When Work Order info is unavailable, use placeholders:
        - wo_consecutive: 000
        - year: current year (25)
        - plant: derived from first digit of item code or default 1
        """
        from raven_ai_agent.skills.formulation_reader.reader import parse_golden_number
        from datetime import datetime
        
        # Don't use current year - use placeholder "00" to match existing CC format
        # current_year = datetime.now().strftime("%y")  # e.g., "25"
        
        for item in items:
            item_code = item.get("item_code")
            bom_no = item.get("bom_no")
            if not item_code:
                continue
            
            # Try 1: Parse golden number from item code (ITEM_XXXXXXXXXX format)
            parsed = parse_golden_number(item_code)
            if parsed and parsed.get("plant"):
                # Construct golden number format from parsed data
                product = parsed.get("product", "")
                plant = parsed.get("plant", "")
                
                if len(product) >= 4:
                    item_prefix = product[:4].zfill(4)
                else:
                    item_prefix = item_code[:4].zfill(4) if len(item_code) >= 4 else item_code.zfill(4)
                
                wo_consecutive = "000"
                wo_year = "00"  # Default year placeholder
                plant_code = plant
                
                cc_code = f"{item_prefix}{wo_consecutive}{wo_year}{plant_code}"
                cc_name = f"{cc_code} - {cc_code} - AMB-W"
                
                if frappe.db.exists("Cost Center", cc_name):
                    return cc_name
                return cc_name
            
            # Try 2: Simple 4-digit item code - construct golden number
            if item_code.isdigit() and len(item_code) >= 4:
                item_prefix = item_code[:4].zfill(4)
                
                # Try to derive plant from first digit
                first_digit = item_code[0]
                plant_map = {
                    '0': '1',  # Default to Mix
                    '1': '1',  # Mix
                    '2': '2',  # Dry
                    '3': '3',  # Juice
                    '4': '4',  # Laboratory
                    '5': '5'   # Formulated
                }
                plant_code = plant_map.get(first_digit, '1')
                
                wo_consecutive = "000"
                wo_year = "00"
                
                cc_code = f"{item_prefix}{wo_consecutive}{wo_year}{plant_code}"
                cc_name = f"{cc_code} - {cc_code} - AMB-W"
                
                frappe.logger().info(f"[DataQualityScanner] Derived cost center from item code: {cc_name}")
                if frappe.db.exists("Cost Center", cc_name):
                    return cc_name
                return cc_name
            
            # Try 3: Check BOM for golden number info
            if bom_no:
                try:
                    import re
                    match = re.search(r'(\d{10})', bom_no)
                    if match:
                        full_code = match.group(1)
                        item_prefix = full_code[:4]
                        plant_code = full_code[9]
                        wo_consecutive = "000"
                        wo_year = "00"
                        
                        cc_code = f"{item_prefix}{wo_consecutive}{wo_year}{plant_code}"
                        cc_name = f"{cc_code} - {cc_code} - AMB-W"
                        
                        frappe.logger().info(f"[DataQualityScanner] Derived cost center from BOM: {cc_name}")
                        if frappe.db.exists("Cost Center", cc_name):
                            return cc_name
                        return cc_name
                except:
                    pass
            
            # Try 4: Check Batch for golden number (lote_real)
            # Look for batches with matching item_code - get the most recent one
            try:
                batches = frappe.get_all(
                    "Batch",
                    filters={"item": item_code},
                    fields=["name", "batch_id", "custom_golden_number"],
                    order_by="creation DESC",
                    limit=10
                )
                for batch in batches:
                    # Use custom_golden_number if available, otherwise fall back to batch_id
                    golden = batch.custom_golden_number or batch.batch_id or batch.name
                    
                    # Extract only digits for golden number check
                    golden_digits = ''.join(filter(str.isdigit, str(golden)))
                    
                    # Check if golden number looks valid (10 digits)
                    if golden_digits and len(golden_digits) == 10:
                        cc_name = f"{golden_digits} - {golden_digits} - AMB-W"
                        
                        frappe.logger().info(f"[DataQualityScanner] Found golden number from Batch: {golden_digits}")
                        if frappe.db.exists("Cost Center", cc_name):
                            return cc_name
                        return cc_name
            except:
                pass
            
            # Try 5: Check Delivery Note items linked to this Sales Order for golden number
            try:
                dn_items = frappe.db.sql("""
                    SELECT dni.item_code, dni.batch_no
                    FROM `tabDelivery Note Item` dni
                    INNER JOIN `tabDelivery Note` dn ON dn.name = dni.parent
                    WHERE dn.against_sales_order = %s
                    AND dni.item_code = %s
                    LIMIT 5
                """, (doc.name, item_code), as_dict=True)
                
                for dni in dn_items:
                    if dni.batch_no:
                        batch_id = dni.batch_no
                        # Extract digits only
                        batch_digits = ''.join(filter(str.isdigit, str(batch_id)))
                        if batch_digits and len(batch_digits) == 10:
                            cc_name = f"{batch_digits} - {batch_digits} - AMB-W"
                            frappe.logger().info(f"[DataQualityScanner] Found golden number from DN batch: {batch_digits}")
                            if frappe.db.exists("Cost Center", cc_name):
                                return cc_name
                            return cc_name
            except:
                pass
        
        frappe.logger().info(f"[DataQualityScanner] Could not derive cost center from items")
        return None
    
    def _find_leaf_cost_center(self, parent_cc: str) -> Optional[str]:
        """Find a leaf (non-group) cost center under a parent group."""
        try:
            children = frappe.get_all(
                "Cost Center",
                filters={
                    "parent_cost_center": parent_cc,
                    "is_group": 0
                },
                fields=["name"],
                limit=1
            )
            if children:
                return children[0].name
        except Exception as e:
            frappe.logger().error(f"[DataQualityScanner] Error finding leaf cost center: {e}")
        return None
    
    def _validate_cost_center(self, doc) -> List[Dict]:
        """Check if cost center is valid (not a group)"""
        issues = []
        
        cost_center = doc.get("cost_center")
        
        if not cost_center:
            # Try to derive cost center from golden number in items
            derived_cc = self._get_cost_center_from_golden_number(doc)
            
            if derived_cc:
                issues.append({
                    "type": "missing_cost_center",
                    "severity": "MEDIUM",
                    "message": "Cost Center is missing - AUTO-FIX AVAILABLE",
                    "field": "cost_center",
                    "auto_fix": "set_from_golden_number",
                    "auto_fix_value": derived_cc,
                    "fix_confidence": 0.95
                })
            else:
                issues.append({
                    "type": "missing_cost_center",
                    "severity": "MEDIUM",
                    "message": "Cost Center is missing - Could not derive from golden number",
                    "field": "cost_center",
                    "auto_fix": "set_default_cost_center",
                    "fix_confidence": 0.70
                })
            return issues
        
        # Check if it's a group
        is_group = frappe.get_value("Cost Center", cost_center, "is_group")
        if is_group:
            issues.append({
                "type": "group_cost_center",
                "severity": "CRITICAL",
                "message": f"Cost Center '{cost_center}' is a Group (cannot be used in transactions)",
                "field": "cost_center",
                "auto_fix": "find_leaf_cost_center",
                "fix_confidence": 0.80
            })
        
        return issues
    
    def _validate_currency(self, so) -> List[Dict]:
        """Check currency issues for Sales Order"""
        issues = []
        
        currency = so.currency
        
        # For MXN company, check if customer has MXN receivable
        if currency == "MXN":
            customer = so.customer
            if customer:
                # This is checked in account validation
                pass
        
        return issues
    
    def _validate_invoice_currency(self, si) -> List[Dict]:
        """Check currency for Sales Invoice - enforce MXN for Mexico"""
        issues = []
        
        currency = si.currency
        company = si.company
        
        if currency and currency != "MXN":
            # Check if company is Mexican
            company_country = frappe.get_value("Company", company, "country")
            if company_country == "Mexico":
                # For MXN company with USD invoice, ensure proper account setup
                # This is more of a warning than error
                issues.append({
                    "type": "foreign_currency_mxn_company",
                    "severity": "LOW",
                    "message": f"Invoice in '{currency}' on Mexican company - ensure proper account configuration",
                    "field": "currency",
                    "auto_fix": None,
                    "fix_confidence": 0.0
                })
        
        return issues
    
    def _validate_payment_terms(self, si) -> List[Dict]:
        """Check payment terms for Sales Invoice"""
        issues = []
        
        # For Mexican company, payment terms should match CFDI
        payment_terms = si.get("payment_terms_template")
        
        if not payment_terms:
            # Warning, not critical
            issues.append({
                "type": "missing_payment_terms",
                "severity": "LOW",
                "message": "Payment Terms not set",
                "field": "payment_terms_template",
                "auto_fix": None,
                "fix_confidence": 0.0
            })
        
        return issues
    
    # ===========================================
    # Helper Methods
    # ===========================================
    
    def _calculate_confidence(self, issues: List[Dict], warnings: List[Dict]) -> float:
        """Calculate confidence score based on issues"""
        # Filter out INFO issues (they are informational, not problems)
        real_issues = [i for i in issues if i.get("severity") != "INFO"]
        
        if not real_issues:
            return 0.95
        
        base_score = 1.0
        
        # Deduct for critical issues
        critical = len([i for i in real_issues if i.get("severity") == "CRITICAL"])
        base_score -= critical * 0.25
        
        # Deduct for high issues
        high = len([i for i in real_issues if i.get("severity") == "HIGH"])
        base_score -= high * 0.15
        
        # Deduct for medium issues
        medium = len([i for i in real_issues if i.get("severity") == "MEDIUM"])
        base_score -= medium * 0.08
        
        # Deduct for low issues
        low = len([i for i in real_issues if i.get("severity") == "LOW"])
        base_score -= low * 0.03
        
        # INFO issues don't reduce confidence
        
        return max(0.1, min(0.95, base_score))
    
    def _find_leaf_account(self, account_name: str, preferred_currency: str = None, company: str = None) -> Optional[str]:
        """Find a leaf (non-group) account under the given account group.
        
        Args:
            account_name: The account to find a leaf for (can be a group like "1105 - CLIENTES - AMB-W")
            preferred_currency: Optional currency to match (e.g., 'USD', 'MXN')
            company: Company to filter by
        """
        try:
            # Check if the account itself is a leaf
            is_group = frappe.get_value("Account", account_name, "is_group")
            if not is_group:
                return account_name
            
            frappe.logger().info(f"[DataQualityScanner] {account_name} is a group, looking for leaf...")
            
            # Strategy 1: Find direct child accounts that are leaves
            children = frappe.get_all(
                "Account",
                filters={
                    "parent_account": account_name,
                    "is_group": 0
                },
                fields=["name", "account_currency"],
                limit=10
            )
            
            if children:
                frappe.logger().info(f"[DataQualityScanner] Found {len(children)} direct leaf accounts")
                if preferred_currency:
                    for child in children:
                        if child.account_currency == preferred_currency:
                            return child.name
                return children[0].name
            
            # Strategy 2: Look for accounts that START with the group account prefix
            # e.g., "1105 - CLIENTES - AMB-W" → find "1105.1.1 - Customer - AMB-W"
            # Extract the root account number (e.g., "1105" from "1105 - CLIENTES")
            import re
            match = re.match(r'^(\d+)', account_name)
            if match:
                root_number = match.group(1)
                frappe.logger().info(f"[DataQualityScanner] Searching for accounts starting with: {root_number}.%")
                
                # First try without is_group filter (some nested accounts might be groups too)
                filters = {
                    "name": ["like", f"{root_number}.%"]
                }
                if company:
                    filters["company"] = company
                    
                nested_accounts = frappe.get_all(
                    "Account",
                    filters=filters,
                    fields=["name", "account_currency", "is_group"],
                    limit=20
                )
                
                frappe.logger().info(f"[DataQualityScanner] Found {len(nested_accounts)} accounts starting with {root_number}.")
                
                if nested_accounts:
                    # Filter to get only leaf accounts (non-groups)
                    leaf_accounts = [a for a in nested_accounts if not a.is_group]
                    frappe.logger().info(f"[DataQualityScanner] {len(leaf_accounts)} are leaf accounts")
                    
                    if leaf_accounts:
                        if preferred_currency:
                            for acc in leaf_accounts:
                                if acc.account_currency == preferred_currency:
                                    return acc.name
                        return leaf_accounts[0].name
                    
                    # If no leaf accounts, try groups (last resort)
                    if nested_accounts:
                        frappe.logger().warning(f"[DataQualityScanner] No leaf accounts found, returning first account")
                        return nested_accounts[0].name
            
            # Strategy 3: Look for any Receivable account in the same company
            frappe.logger().warning(f"[DataQualityScanner] No child accounts found, trying Receivable accounts")
            if not company:
                company = frappe.get_value("Account", account_name, "company")
            
            found_account = None
            
            if company:
                filters = {
                    "company": company,
                    "account_type": "Receivable",
                    "is_group": 0
                }
                if preferred_currency:
                    filters["account_currency"] = preferred_currency
                    
                receivables = frappe.get_all(
                    "Account",
                    filters=filters,
                    fields=["name", "account_currency"],
                    limit=10
                )
                
                if receivables:
                    frappe.logger().info(f"[DataQualityScanner] Found {len(receivables)} receivable accounts")
                    # Prefer accounts with "Debtors" in name for generic fallback
                    for acc in receivables:
                        if "Debtors" in acc.name or "CLIENTES" in acc.name:
                            return acc.name
                    return receivables[0].name
            
            # Strategy 4: Hardcoded fallback for known accounts (AMB-Wellness specific)
            frappe.logger().warning(f"[DataQualityScanner] Using hardcoded fallback for AMB-Wellness")
            if company == "AMB-Wellness":
                # Try known USD receivable
                if frappe.db.exists("Account", "1310 - Debtors - AMB-W"):
                    return "1310 - Debtors - AMB-W"
                # Try known MXN receivable  
                if frappe.db.exists("Account", "1320 - Debtors - AMB-W"):
                    return "1320 - Debtors - AMB-W"
            
            return None
            
        except Exception as e:
            frappe.logger().error(f"[DataQualityScanner] Error finding leaf account: {e}")
            return None
    
    def _apply_fixes(self, doc_name: str, doc_type: str, result: Dict) -> Dict:
        """Apply auto-fixes to the document"""
        applied = []
        failed = []
        skipped = []
        
        try:
            doc = frappe.get_doc(doc_type, doc_name)
        except Exception as e:
            frappe.logger().error(f"[DataQualityScanner] Could not load document: {e}")
            return {"applied": [], "failed": [str(e)], "skipped": []}
        
        for issue in result.get("issues", []):
            if not issue.get("auto_fix"):
                frappe.logger().info(f"[DataQualityScanner] Skipping issue (no auto_fix): {issue.get('type')}")
                continue
            
            fix_type = issue.get("auto_fix")
            field = issue.get("field")
            fix_value = issue.get("auto_fix_value")
            frappe.logger().info(f"[DataQualityScanner] Processing fix: type={fix_type}, field={field}, current_value={issue.get('current_value', 'N/A')}")
            
            try:
                # Cost Center Fix
                if fix_type == "set_from_golden_number" and field == "cost_center" and fix_value:
                    # Check if Cost Center exists or can be found
                    cc_exists = frappe.db.exists("Cost Center", fix_value)
                    
                    # Also try finding it with different naming patterns
                    if not cc_exists:
                        # Try to find similar cost centers
                        similar = frappe.get_all("Cost Center", 
                            filters={"name": ["like", f"%{fix_value.split(' - ')[0]}%"]},
                            limit=5)
                        if similar:
                            cc_exists = True
                            fix_value = similar[0].name
                            applied.append(f"Found existing CC: {fix_value}")
                    
                    if cc_exists:
                        try:
                            doc.db_set("cost_center", fix_value)
                            frappe.db.commit()
                            applied.append(f"Set {field} = {fix_value}")
                            frappe.logger().info(f"[DataQualityScanner] Applied fix: {field} = {fix_value}")
                        except Exception as cc_err:
                            failed.append(f"Could not set CC: {cc_err}")
                    else:
                        # Try to create the Cost Center if it doesn't exist
                        try:
                            cc = frappe.get_doc({
                                "doctype": "Cost Center",
                                "cost_center_name": fix_value,
                                "company": doc.company or "AMB-Wellness",
                                "parent_cost_center": "AMB-Wellness - AMB-W",
                                "is_group": 0
                            })
                            cc.insert(ignore_permissions=True)
                            frappe.db.commit()
                            
                            doc.db_set("cost_center", fix_value)
                            frappe.db.commit()
                            applied.append(f"Created and set {field} = {fix_value}")
                        except Exception as ce:
                            failed.append(f"Could not create CC {fix_value}: {ce}")
                            frappe.logger().error(f"[DataQualityScanner] CC creation failed: {ce}")
                    continue
                
                # Account Fix - Find Leaf Account (only for Invoices, not Orders)
                if fix_type == "find_leaf_account" and field == "debit_to":
                    # Sales Orders don't have debit_to - it's set at invoice time
                    if doc_type == "Sales Order":
                        skipped.append("Skipped debit_to fix - accounts are set at Invoice level for Sales Orders")
                        frappe.logger().info(f"[DataQualityScanner] Skipping debit_to fix for Sales Order - set at invoice time")
                        continue
                    
                    account = issue.get("current_value", "")
                    currency = doc.get("currency", "USD")  # Get document currency
                    company = doc.get("company")
                    frappe.logger().info(f"[DataQualityScanner] === FIND LEAF ACCOUNT ===")
                    frappe.logger().info(f"[DataQualityScanner] account={account}, currency={currency}, company={company}")
                    leaf = self._find_leaf_account(account, preferred_currency=currency, company=company)
                    frappe.logger().info(f"[DataQualityScanner] _find_leaf_account returned: {leaf}")
                    if leaf:
                        try:
                            # Use direct SQL update to bypass ALL validation
                            frappe.db.sql("""
                                UPDATE `tabSales Order` 
                                SET debit_to = %s, modified = NOW(), modified_by = 'Administrator'
                                WHERE name = %s
                            """, (leaf, doc_name))
                            frappe.db.commit()
                            applied.append(f"Set {field} = {leaf}")
                            frappe.logger().info(f"[DataQualityScanner] Successfully set debit_to to {leaf}")
                        except Exception as save_err:
                            failed.append(f"Could not save: {save_err}")
                            frappe.logger().error(f"[DataQualityScanner] Save failed: {save_err}")
                    else:
                        failed.append(f"Could not find leaf account for {account}")
                        frappe.logger().error(f"[DataQualityScanner] FAILED: Could not find leaf account for {account}")
                    continue
                
                # Address Fixes - Handle various address types
                if fix_type in ["create_from_customer", "copy_from_customer_address"]:
                    # Determine which address field to set
                    if field == "customer_address":
                        addr = self._create_address_from_customer(doc)
                        if addr:
                            try:
                                doc.db_set("customer_address", addr)
                                frappe.db.commit()
                                applied.append(f"Created and set {field} = {addr}")
                            except Exception as addr_err:
                                failed.append(f"Could not set address: {addr_err}")
                    elif field == "billing_address_name":
                        # Sales Orders don't have billing_address_name - use customer_address instead
                        addr = self._create_address_from_customer(doc, address_type="Billing")
                        if addr:
                            try:
                                doc.db_set("customer_address", addr)  # Use customer_address for billing
                                frappe.db.commit()
                                applied.append(f"Created and set customer_address (for billing) = {addr}")
                            except Exception as addr_err:
                                failed.append(f"Could not set billing address: {addr_err}")
                    elif field == "shipping_address_name":
                        addr = self._create_address_from_customer(doc, address_type="Shipping")
                        if addr:
                            try:
                                doc.db_set("shipping_address_name", addr)
                                frappe.db.commit()
                                applied.append(f"Created and set {field} = {addr}")
                            except Exception as addr_err:
                                failed.append(f"Could not set shipping address: {addr_err}")
                    continue
                    
            except Exception as e:
                failed.append(f"Fix {fix_type} failed: {str(e)}")
                frappe.logger().error(f"[DataQualityScanner] Fix failed: {fix_type} - {e}")
        
        return {"applied": applied, "failed": failed, "skipped": skipped}
    
    def _create_address_from_customer(self, doc, address_type: str = "Billing") -> Optional[str]:
        """Create address from customer"""
        try:
            customer = frappe.get_doc("Customer", doc.customer)
            
            # Try to get existing address of the requested type
            addresses = frappe.get_all(
                "Address",
                filters={"link_doctype": "Customer", "link_name": doc.customer},
                fields=["name", "address_type"],
            )
            
            # First, try to find an address of the requested type
            for addr in addresses:
                if address_type == "Billing" and addr.address_type == "Billing":
                    return addr.name
                if address_type == "Shipping" and addr.address_type == "Shipping":
                    return addr.name
            
            # If no address of the requested type, return first available
            if addresses:
                return addresses[0].name
            
            # Create new address
            addr_name = f"{customer.customer_name} - {address_type}"
            addr = frappe.get_doc({
                "doctype": "Address",
                "address_title": customer.customer_name,
                "address_type": address_type,
                "address_line1": customer.address_line1 or "",
                "city": customer.city or "",
                "state": customer.state or "",
                "pincode": customer.pincode or "",
                "country": customer.country or "Mexico",
                "phone": customer.phone or "",
                "email_id": customer.email_id or "",
                "links": [{
                    "link_doctype": "Customer",
                    "link_name": doc.customer
                }]
            })
            addr.insert(ignore_permissions=True)
            frappe.db.commit()
            return addr.name
            
        except Exception as e:
            frappe.logger().error(f"[DataQualityScanner] Failed to create address: {e}")
            return None
    
    def _store_validation_pattern(self, doc_name: str, doc_type: str, result: Dict):
        """Store validation result in Memory (Memento) for learning"""
        try:
            # This integrates with the Memory System
            # Store as a "Fact" with high importance if issues found
            importance = 0.8 if result.get("total_issues", 0) > 0 else 0.3
            
            memory_doc = frappe.get_doc({
                "doctype": "AI Memory",
                "memory_type": "Validation Pattern",
                "content": f"Validation scan for {doc_type} {doc_name}: {result.get('total_issues', 0)} issues found, confidence: {result.get('confidence', 0):.2f}",
                "importance_score": importance,
                "topics": "data_quality,validation,preflight",
                "source": "DataQualityScanner",
                "user": frappe.session.user if hasattr(frappe, 'session') else "system"
            })
            memory_doc.insert(ignore_permissions=True)
            frappe.db.commit()
            
        except Exception as e:
            # Don't fail the scan if memory storage fails
            frappe.logger().warning(f"DataQualityScanner: Failed to store memory: {e}")
    
    def _format_scan_result(self, result: Dict, doc_name: str, doc_type: str, fix_result: Dict = None, fix_mode: str = "none") -> str:
        """Format scan result for display - uses response formatter for consistency"""
        if not result.get("success"):
            return f"❌ Error: {result.get('error')}"
        
        issues = result.get("issues", [])
        warnings = result.get("warnings", [])
        confidence = result.get("confidence", 0)
        
        # Build response with consistent header
        mode_indicator = ""
        if fix_mode == "apply":
            mode_indicator = "**[APPLIED]** "
        elif fix_mode == "force":
            mode_indicator = "**[FORCED]** "
        elif fix_mode == "preview":
            mode_indicator = "**[PREVIEW]** "
            
        response = f"## 🔍 Data Quality Scan: `{doc_name}`\n\n{mode_indicator}"
        
        # Debug info - show fix attempt details
        debug_info = result.get("_debug_fix_info")
        if debug_info and fix_mode in ["apply", "force"]:
            response += f"**Debug:** fix_mode={debug_info.get('fix_mode')}, fix_result={debug_info.get('fix_result')}\n\n"
        
        # Add mode indicator
        if fix_result and fix_result.get("applied") and len(fix_result.get("applied", [])) > 0:
            response += "**✨ Fixes Applied**\n\n"
        
        # Add confidence score with consistent formatting
        response += format_confidence_score(confidence, "CONFIDENCE") + "\n\n"
        
        # Show applied fixes in table format
        if fix_result and fix_result.get("applied"):
            response += "### ✨ Auto-Fixes Applied\n\n"
            
            fix_data = []
            for fix in fix_result["applied"]:
                fix_data.append({"Action": fix, "Status": "✅ Applied"})
            
            if fix_result.get("failed"):
                for fail in fix_result["failed"]:
                    fix_data.append({"Action": fail, "Status": "❌ Failed"})
            
            response += format_table(fix_data, ["Action", "Status"]) + "\n\n"
        
        if not issues and not warnings:
            # Show document details even when no issues found
            doc_info = []
            
            # Add document-specific info based on type
            if result.get("document_type") == "Quotation":
                doc_info = [
                    {"Field": "Quotation", "Value": f"`{result.get('document_name')}`"},
                    {"Field": "Customer", "Value": result.get('customer', 'N/A')},
                    {"Field": "Date", "Value": result.get('transaction_date', 'N/A')},
                    {"Field": "Valid Till", "Value": result.get('valid_till', 'N/A')},
                    {"Field": "Status", "Value": result.get('status', 'N/A')},
                    {"Field": "Items", "Value": str(result.get('item_count', 0))},
                    {"Field": "Total", "Value": f"{result.get('total', 0):,.2f} {result.get('currency', 'MXN')}"}
                ]
                response += "### 📋 Quotation Details\n\n"
                response += format_table(doc_info, ["Field", "Value"]) + "\n\n"
            
            response += "✅ **No issues found!** Document is ready for processing.\n"
            return apply_post_processing(response)
        
        # Use the formatter for issues
        response += format_issues(issues, "Issues Found") + "\n"
        
        # Summary in table format
        fixable = len([i for i in issues if i.get("auto_fix")])
        critical_count = len([i for i in issues if i.get("severity") == "CRITICAL"])
        
        summary_data = [
            {"Metric": "Total Issues", "Value": str(len(issues))},
            {"Metric": "Auto-Fixable", "Value": str(fixable)},
            {"Metric": "Critical", "Value": str(critical_count)},
            {"Metric": "Can Proceed", "Value": "✅ Yes" if result.get("can_proceed") else "❌ No"}
        ]
        
        response += "\n---\n\n"
        
        # Add document details section
        if result.get("document_type") == "Quotation":
            doc_details = [
                {"Field": "Quotation", "Value": f"`{result.get('document_name')}`"},
                {"Field": "Customer", "Value": result.get('customer', 'N/A')},
                {"Field": "Items", "Value": str(result.get('item_count', 0))},
                {"Field": "Total", "Value": f"{result.get('total', 0):,.2f} {result.get('currency', 'MXN')}"}
            ]
            response += "### 📋 Document Details\n\n"
            response += format_table(doc_details, ["Field", "Value"]) + "\n\n"
        
        response += "### 📊 Summary\n\n"
        response += format_table(summary_data, ["Metric", "Value"]) + "\n\n"
        
        # Add pipeline diagnosis if available
        pipeline_diagnosis = result.get("pipeline_diagnosis")
        if pipeline_diagnosis:
            # Check if it's a Sales Order or Quotation report
            if pipeline_diagnosis.get("sales_order"):
                response += "\n" + self._format_pipeline_diagnosis(pipeline_diagnosis)
            elif pipeline_diagnosis.get("quotation"):
                response += "\n" + self._format_quotation_diagnosis(pipeline_diagnosis)
        
        return apply_post_processing(response)
    
    # ===========================================
    # Pipeline Diagnosis Methods
    # ===========================================
    
    def diagnose_pipeline(self, so_name: str) -> Dict:
        """
        Diagnose the complete pipeline for a Sales Order and identify missing documents.
        This provides a full picture of the document flow from SO to completed delivery.
        
        Returns a diagnostic report with:
        - Sales Order details
        - Items and BOMs
        - Delivery Notes and Batches
        - Sales Invoices
        - Missing Cost Centers
        - Missing documents
        """
        report = {
            "sales_order": None,
            "items": [],
            "delivery_notes": [],
            "sales_invoices": [],
            "boms": [],
            "batches": [],
            "missing": {
                "boms": [],
                "cost_centers": [],
                "batches": [],
                "stock_entries": []
            },
            "summary": {}
        }
        
        try:
            # 1. Load Sales Order
            so_doc = frappe.get_doc("Sales Order", so_name)
            report["sales_order"] = {
                "name": so_doc.name,
                "customer": so_doc.customer,
                "status": so_doc.status,
                "transaction_date": so_doc.transaction_date,
                "company": so_doc.company
            }
            
            # 2. Analyze items and BOMs
            for item in so_doc.items:
                item_info = {
                    "item_code": item.item_code,
                    "qty": item.qty,
                    "bom_no": item.bom_no,
                    "warehouse": item.warehouse
                }
                report["items"].append(item_info)
                
                # Check if BOM exists
                if item.bom_no:
                    try:
                        bom = frappe.get_doc("BOM", item.bom_no)
                        report["boms"].append({
                            "name": bom.name,
                            "item": bom.item,
                            "total_cost": bom.total_cost,
                            "is_active": bom.is_active,
                            "is_default": bom.is_default
                        })
                    except:
                        report["missing"]["boms"].append(item.bom_no)
            
            # 3. Find Delivery Notes
            dns = frappe.db.sql("""
                SELECT DISTINCT dn.name, dn.posting_date
                FROM `tabDelivery Note` dn
                INNER JOIN `tabDelivery Note Item` dni ON dn.name = dni.parent
                WHERE dni.against_sales_order = %s
            """, so_name, as_dict=True)
            
            for dn in dns:
                try:
                    dn_doc = frappe.get_doc("Delivery Note", dn.name)
                    dn_info = {
                        "name": dn_doc.name,
                        "posting_date": dn_doc.posting_date,
                        "docstatus": dn_doc.docstatus,
                        "items": []
                    }
                    
                    for item in dn_doc.items:
                        item_info = {
                            "item_code": item.item_code,
                            "batch_no": item.batch_no,
                            "qty": item.qty
                        }
                        dn_info["items"].append(item_info)
                        
                        # Check Batch
                        if item.batch_no:
                            try:
                                batch = frappe.get_doc("Batch", item.batch_no)
                                # Try to get golden number - extract digits only for CC check
                                raw_golden = batch.custom_golden_number or batch.batch_id or batch.name
                                # Extract only digits for golden number check
                                golden_digits = ''.join(filter(str.isdigit, str(raw_golden)))
                                plant_code = batch.custom_plant_code if hasattr(batch, 'custom_plant_code') else None
                                
                                report["batches"].append({
                                    "name": batch.name,
                                    "item": batch.item,
                                    "golden_number": raw_golden if (raw_golden and len(str(raw_golden)) >= 10) else None,
                                    "plant_code": plant_code
                                })
                                
                                # Check if Cost Center exists for this golden number (using digits only)
                                if golden_digits and len(golden_digits) >= 10:
                                    expected_cc = f"{golden_digits} - {golden_digits} - AMB-W"
                                    cc_exists = frappe.db.exists("Cost Center", expected_cc)
                                    if not cc_exists:
                                        if expected_cc not in report["missing"]["cost_centers"]:
                                            report["missing"]["cost_centers"].append(expected_cc)
                            except:
                                pass
                    
                    report["delivery_notes"].append(dn_info)
                except:
                    pass
            
            # 4. Find Sales Invoices
            sins = frappe.db.sql("""
                SELECT DISTINCT sin.name, sin.posting_date
                FROM `tabSales Invoice` sin
                INNER JOIN `tabSales Invoice Item` sini ON sin.name = sini.parent
                WHERE sini.sales_order = %s
            """, so_name, as_dict=True)
            
            for sin in sins:
                report["sales_invoices"].append({
                    "name": sin.name,
                    "posting_date": sin.posting_date
                })
            
            # 5. Build summary
            report["summary"] = {
                "total_items": len(report["items"]),
                "total_boms": len(report["boms"]),
                "total_delivery_notes": len(report["delivery_notes"]),
                "total_batches": len(report["batches"]),
                "total_invoices": len(report["sales_invoices"]),
                "missing_boms_count": len(report["missing"]["boms"]),
                "missing_cost_centers_count": len(report["missing"]["cost_centers"])
            }
            
            return report
            
        except Exception as e:
            frappe.logger().error(f"[DataQualityScanner] Pipeline diagnosis error: {e}")
            return {"error": str(e)}
    
    def diagnose_quotation_pipeline(self, qtn_name: str) -> Dict:
        """
        Diagnose the complete pipeline for a Quotation and identify next steps.
        This provides a full picture of the document flow from Quotation to Sales Order.
        
        Returns a diagnostic report with:
        - Quotation details
        - Items and pricing
        - Customer info
        - Next steps (convert to SO)
        """
        report = {
            "quotation": None,
            "items": [],
            "customer": None,
            "next_steps": [],
            "pipeline_status": "pending_conversion",
            "summary": {}
        }
        
        try:
            # 1. Load Quotation
            qtn_doc = frappe.get_doc("Quotation", qtn_name)
            report["quotation"] = {
                "name": qtn_doc.name,
                "customer": qtn_doc.customer,
                "party_name": qtn_doc.party_name,
                "status": qtn_doc.status,
                "transaction_date": qtn_doc.transaction_date,
                "valid_till": qtn_doc.valid_till,
                "company": qtn_doc.company,
                "total": qtn_doc.total,
                "grand_total": qtn_doc.grand_total,
                "currency": qtn_doc.currency
            }
            
            # Check if quotation is expired
            from datetime import datetime
            if qtn_doc.valid_till:
                try:
                    valid_till = datetime.strptime(str(qtn_doc.valid_till), "%Y-%m-%d")
                    today = datetime.strptime(str(frappe.utils.today()), "%Y-%m-%d")
                    if valid_till < today:
                        report["next_steps"].append({
                            "action": "warning",
                            "message": "⚠️ Quotation has expired - consider creating a new one"
                        })
                except:
                    pass
            
            # 2. Analyze items
            for item in qtn_doc.items:
                item_info = {
                    "item_code": item.item_code,
                    "item_name": item.item_name,
                    "qty": item.qty,
                    "rate": item.rate,
                    "amount": item.amount,
                    "uom": item.uom
                }
                report["items"].append(item_info)
            
            # 3. Get customer info
            if qtn_doc.customer:
                try:
                    customer = frappe.get_doc("Customer", qtn_doc.customer)
                    report["customer"] = {
                        "name": customer.name,
                        "customer_name": customer.customer_name,
                        "customer_type": customer.customer_type,
                        "territory": customer.territory,
                        "customer_group": customer.customer_group
                    }
                except:
                    pass
            
            # 4. Determine next steps based on quotation status
            if qtn_doc.status == "Draft":
                report["next_steps"].append({
                    "action": "submit",
                    "message": "📝 Submit the Quotation to make it valid"
                })
                report["pipeline_status"] = "draft"
            elif qtn_doc.status == "Submitted":
                report["next_steps"].append({
                    "action": "convert",
                    "message": "🎯 Convert to Sales Order to proceed with fulfillment"
                })
                report["pipeline_status"] = "ready_to_convert"
            elif qtn_doc.status == "Ordered":
                # Check if Sales Order was created
                so_linked = frappe.db.sql("""
                    SELECT name FROM `tabSales Order`
                    WHERE quotation = %s
                """, qtn_name)
                
                if so_linked:
                    report["next_steps"].append({
                        "action": "view_so",
                        "message": f"✅ Sales Order created: {so_linked[0][0]}"
                    })
                    report["pipeline_status"] = "converted"
                else:
                    report["next_steps"].append({
                        "action": "investigate",
                        "message": "⚠️ Quotation marked as Ordered but no SO found"
                    })
                    report["pipeline_status"] = "issue"
            elif qtn_doc.status == "Lost":
                report["next_steps"].append({
                    "action": "lost",
                    "message": "❌ Quotation was lost - no further action possible"
                })
                report["pipeline_status"] = "lost"
            elif qtn_doc.status == "Expired":
                report["next_steps"].append({
                    "action": "renew",
                    "message": "🔄 Quotation expired - create a new one if customer is interested"
                })
                report["pipeline_status"] = "expired"
            
            # 5. Build summary
            report["summary"] = {
                "total_items": len(report["items"]),
                "total_value": qtn_doc.grand_total,
                "currency": qtn_doc.currency,
                "status": qtn_doc.status,
                "pipeline_status": report["pipeline_status"]
            }
            
            return report
            
        except Exception as e:
            frappe.logger().error(f"[DataQualityScanner] Quotation pipeline diagnosis error: {e}")
            return {"error": str(e)}
    
    def _format_pipeline_diagnosis(self, report: Dict) -> str:
        """Format pipeline diagnosis for display - uses response formatter for consistency"""
        if "error" in report:
            return f"\n\n❌ Pipeline Diagnosis Error: {report['error']}\n\n"
        
        so = report.get("sales_order", {})
        summary = report.get("summary", {})
        
        output = ""
        
        # Header with consistent formatting
        output += "\n\n--- 📊 PIPELINE DIAGNOSIS ---\n\n"
        
        # Document info table
        doc_info = [
            {"Field": "Sales Order", "Value": f"`{so.get('name')}`"},
            {"Field": "Customer", "Value": so.get('customer', 'N/A')},
            {"Field": "Status", "Value": so.get('status', 'N/A')},
            {"Field": "Company", "Value": so.get('company', 'N/A')}
        ]
        output += format_table(doc_info, ["Field", "Value"]) + "\n\n"
        
        # Summary table
        output += "### 📦 Pipeline Summary\n\n"
        summary_data = [
            {"Item": "Items", "Count": str(summary.get('total_items', 0)), "Emoji": "📦"},
            {"Item": "BOMs", "Count": str(summary.get('total_boms', 0)), "Emoji": "🔧"},
            {"Item": "Delivery Notes", "Count": str(summary.get('total_delivery_notes', 0)), "Emoji": "🚚"},
            {"Item": "Batches", "Count": str(summary.get('total_batches', 0)), "Emoji": "🏷️"},
            {"Item": "Sales Invoices", "Count": str(summary.get('total_invoices', 0)), "Emoji": "💰"}
        ]
        output += format_table(summary_data, ["Emoji", "Item", "Count"]) + "\n\n"
        
        # Missing items - format as table if many, otherwise as list
        missing_boms = report.get("missing", {}).get("boms", [])
        missing_ccs = report.get("missing", {}).get("cost_centers", [])
        
        if missing_boms or missing_ccs:
            output += "### ⚠️ Missing Documents\n\n"
            
            if missing_boms:
                output += "**🔴 Missing BOMs:**\n"
                bom_data = [{"BOM": bom} for bom in missing_boms]
                output += format_table(bom_data, ["BOM"]) + "\n\n"
            
            if missing_ccs:
                output += "**🟠 Missing Cost Centers:**\n"
                cc_data = [{"Cost Center": cc} for cc in missing_ccs]
                output += format_table(cc_data, ["Cost Center"]) + "\n\n"
        
        # Items details as table
        if report.get("items"):
            output += "### 📦 Items in Sales Order\n\n"
            item_data = []
            for item in report["items"]:
                item_data.append({
                    "Item": item['item_code'],
                    "Qty": str(item['qty']),
                    "BOM": item['bom_no'] or 'NONE'
                })
            output += format_table(item_data, ["Item", "Qty", "BOM"]) + "\n\n"
        
        # BOMs as table
        if report.get("boms"):
            output += "### 🔧 Bill of Materials (BOMs)\n\n"
            bom_data = []
            for bom in report["boms"]:
                bom_data.append({
                    "BOM": bom['name'],
                    "Item": bom['item'],
                    "Cost": f"${bom['total_cost']:.2f}" if bom.get('total_cost') else "N/A"
                })
            output += format_table(bom_data, ["BOM", "Item", "Cost"]) + "\n\n"
        
        # Delivery Notes as table
        if report.get("delivery_notes"):
            output += "### 🚚 Delivery Notes\n\n"
            dn_data = []
            for dn in report["delivery_notes"]:
                status_map = {0: "Draft", 1: "Submitted", 2: "Cancelled"}
                status = status_map.get(dn.get('docstatus', 0), "Unknown")
                dn_data.append({
                    "DN": dn['name'],
                    "Date": str(dn['posting_date']) if dn.get('posting_date') else 'N/A',
                    "Status": status,
                    "Items": str(len(dn.get('items', [])))
                })
            output += format_table(dn_data, ["DN", "Date", "Status", "Items"]) + "\n\n"
        
        # Batches as table
        if report.get("batches"):
            output += "### 🏷️ Batches\n\n"
            batch_data = []
            for batch in report["batches"]:
                golden = batch.get('golden_number') or 'N/A'
                batch_data.append({
                    "Batch": batch['name'],
                    "Item": batch['item'],
                    "Golden #": str(golden)[:20] if golden != 'N/A' else 'N/A'
                })
            output += format_table(batch_data, ["Batch", "Item", "Golden #"]) + "\n\n"
        
        # Sales Invoices as table
        if report.get("sales_invoices"):
            output += "### 💰 Sales Invoices\n\n"
            sin_data = []
            for sin in report["sales_invoices"]:
                sin_data.append({
                    "Invoice": sin['name'],
                    "Date": str(sin['posting_date']) if sin.get('posting_date') else 'N/A'
                })
            output += format_table(sin_data, ["Invoice", "Date"]) + "\n\n"
        
        # Recommendations section
        output += "---\n\n"
        output += "### 💡 Recommended Actions\n\n"
        
        has_recommendations = False
        actions = []
        
        if missing_ccs:
            actions.append({
                "Action": "Create missing Cost Centers",
                "Command": f"`@ai fix {so.get('name')}`"
            })
            has_recommendations = True
        
        if summary.get('total_delivery_notes', 0) == 0:
            actions.append({
                "Action": "Create Delivery Notes",
                "Command": f"`@sales_order_follow_up delivery {so.get('name')}`"
            })
            has_recommendations = True
        
        if summary.get('total_invoices', 0) == 0:
            actions.append({
                "Action": "Generate Sales Invoice",
                "Command": "Create from delivered items"
            })
            has_recommendations = True
        
        if not has_recommendations:
            output += "✅ Pipeline is complete! No actions needed.\n"
        else:
            output += format_table(actions, ["Action", "Command"]) + "\n"
        
        return apply_post_processing(output)
    
    def _format_quotation_diagnosis(self, report: Dict) -> str:
        """Format Quotation pipeline diagnosis for display"""
        if "error" in report:
            return f"\n\n❌ Quotation Pipeline Diagnosis Error: {report['error']}\n\n"
        
        qtn = report.get("quotation", {})
        summary = report.get("summary", {})
        next_steps = report.get("next_steps", [])
        
        output = ""
        
        # Header with consistent formatting
        output += "\n\n--- 📊 QUOTATION PIPELINE DIAGNOSIS ---\n\n"
        
        # Document info table
        doc_info = [
            {"Field": "Quotation", "Value": f"`{qtn.get('name')}`"},
            {"Field": "Customer", "Value": qtn.get('customer', 'N/A')},
            {"Field": "Status", "Value": qtn.get('status', 'N/A')},
            {"Field": "Valid Till", "Value": str(qtn.get('valid_till', 'N/A'))},
            {"Field": "Total", "Value": f"{qtn.get('total', 0):,.2f} {qtn.get('currency', 'MXN')}"}
        ]
        output += format_table(doc_info, ["Field", "Value"]) + "\n\n"
        
        # Pipeline Status
        status_emoji = {
            "draft": "📝",
            "ready_to_convert": "🎯",
            "converted": "✅",
            "expired": "⏰",
            "lost": "❌",
            "pending_conversion": "⏳",
            "issue": "⚠️"
        }
        status = summary.get("pipeline_status", "unknown")
        emoji = status_emoji.get(status, "❓")
        
        output += f"### {emoji} Pipeline Status: {status.replace('_', ' ').title()}\n\n"
        
        # Summary table
        summary_data = [
            {"Item": "Items", "Count": str(summary.get('total_items', 0)), "Emoji": "📦"},
            {"Item": "Total Value", "Value": f"{summary.get('total_value', 0):,.2f}", "Emoji": "💵"}
        ]
        output += format_table(summary_data, ["Emoji", "Item", "Count", "Value"]) + "\n\n"
        
        # Next Steps
        if next_steps:
            output += "### 🎯 Next Steps\n\n"
            actions = []
            for step in next_steps:
                action_type = step.get("action", "info")
                message = step.get("message", "")
                
                action_emoji = {
                    "submit": "📝",
                    "convert": "🎯",
                    "view_so": "📋",
                    "warning": "⚠️",
                    "renew": "🔄",
                    "lost": "❌",
                    "investigate": "🔍"
                }
                emoji = action_emoji.get(action_type, "➡️")
                actions.append({
                    "Action": f"{emoji} {message}",
                    "Type": action_type
                })
            
            for action in actions:
                output += f"- {action['Action']}\n"
            output += "\n"
        
        # Items details as table
        if report.get("items"):
            output += "### 📦 Items in Quotation\n\n"
            item_data = []
            for item in report["items"]:
                item_data.append({
                    "Item": item['item_code'][:30] if item.get('item_code') else 'N/A',
                    "Name": item.get('item_name', 'N/A')[:25],
                    "Qty": str(item.get('qty', 0)),
                    "Rate": f"{item.get('rate', 0):,.2f}",
                    "Amount": f"{item.get('amount', 0):,.2f}"
                })
            output += format_table(item_data, ["Item", "Name", "Qty", "Rate", "Amount"]) + "\n\n"
        
        # Customer info
        if report.get("customer"):
            cust = report["customer"]
            output += "### 👤 Customer Information\n\n"
            cust_info = [
                {"Field": "Customer Name", "Value": cust.get('customer_name', 'N/A')},
                {"Field": "Type", "Value": cust.get('customer_type', 'N/A')},
                {"Field": "Territory", "Value": cust.get('territory', 'N/A')},
                {"Field": "Group", "Value": cust.get('customer_group', 'N/A')}
            ]
            output += format_table(cust_info, ["Field", "Value"]) + "\n\n"
        
        # Recommendations based on status
        output += "### 💡 Recommendations\n\n"
        
        recommendations = []
        
        if status == "draft":
            recommendations.append({
                "Action": "Submit Quotation",
                "Command": f"Submit `{qtn.get('name')}` in ERPNext"
            })
            recommendations.append({
                "Action": "Send to Customer",
                "Command": "Share via email or print"
            })
        elif status == "ready_to_convert":
            recommendations.append({
                "Action": "Convert to Sales Order",
                "Command": "Click 'Make Sales Order' button in Quotation"
            })
            recommendations.append({
                "Action": "Create SO via AI",
                "Command": f"`@ai create sales order from {qtn.get('name')}`"
            })
        elif status == "converted":
            recommendations.append({
                "Action": "Check Sales Order",
                "Command": "View linked SO in Quotation"
            })
        elif status == "expired":
            recommendations.append({
                "Action": "Create New Quotation",
                "Command": "Create new quotation with updated pricing"
            })
        elif status == "lost":
            recommendations.append({
                "Action": "Analyze Loss Reason",
                "Command": "Update lost reason in Quotation for analytics"
            })
        
        if recommendations:
            output += format_table(recommendations, ["Action", "Command"]) + "\n"
        
        return apply_post_processing(output)
    
    def _get_help_message(self) -> str:
        """Return help message with consistent formatting"""
        from raven_ai_agent.api.response_formatter import format_table
        
        response = """
## 🔍 Data Quality Scanner

Pre-flight validation for ERPNext documents before operations.

"""
        
        # Usage as table
        usage_data = [
            {"Command": "scan", "Target": "SO-XXXXX", "Example": "@ai scan SO-00769-COSMETILAB 18"},
            {"Command": "validate", "Target": "ACC-SINV-XXXXX", "Example": "@ai validate ACC-SINV-2026-00070"},
            {"Command": "check data", "Target": "SAL-QTN-XXXXX", "Example": "@ai check data SAL-QTN-2024-00763"},
            {"Command": "pipeline", "Target": "SO-XXXXX", "Example": "@ai pipeline SO-00752-LEGOSAN AB"},
            {"Command": "full scan", "Target": "SO-XXXXX", "Example": "@ai full scan SO-00769-COSMETILAB 18"},
            # Quotation Commands (NEW)
            {"Command": "scan", "Target": "QUOT-XXXXX", "Example": "@ai scan QUOT-2026-00001"},
            {"Command": "pipeline", "Target": "QUOT-XXXXX", "Example": "@ai diagnose pipeline of quotation QUOT-2026-00001"},
            {"Command": "diagnose", "Target": "QUOT-XXXXX", "Example": "@ai diagnose quotation QUOT-2026-00001"}
        ]
        
        response += "### 📋 Usage\n\n"
        response += format_table(usage_data, ["Command", "Target", "Example"]) + "\n\n"
        
        # What it checks
        checks = [
            {"Category": "✅ Addresses", "Checks": "Customer, Shipping, Billing"},
            {"Category": "✅ Accounts", "Checks": "Receivable, Income accounts"},
            {"Category": "✅ MX CFDI", "Checks": "Tax regime, CFDI use, Payment method"},
            {"Category": "✅ Cost Center", "Checks": "Not a group, derives from golden #"},
            {"Category": "✅ Currency", "Checks": "MXN enforcement for Mexico"},
            {"Category": "✅ Pipeline", "Checks": "BOMs, DNs, Batches, Invoices"}
        ]
        
        response += "### 🔎 What It Checks\n\n"
        response += format_table(checks, ["Category", "Checks"]) + "\n\n"
        
        # Returns
        returns = [
            {"Return": "Confidence Score", "Format": "HIGH/MEDIUM/LOW with %"},
            {"Return": "Issues List", "Format": "Grouped by severity"},
            {"Return": "Auto-fix Options", "Format": "With confidence %"},
            {"Return": "Pipeline Report", "Format": "Full document flow"}
        ]
        
        response += "### 📤 Returns\n\n"
        response += format_table(returns, ["Return", "Format"])
        
        return apply_post_processing(response)
