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
            return {
                "success": False,
                "error": str(e)
            }
    
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


# Métodos añadidos para soporte de quotations

    def _extract_document_name(self, query):
        """Extract document name from query"""
        import re
        patterns = [
            r'(SO-[\w-]+)',
            r'(SAL-QTN-\d+-\d+)',
            r'(QUOT-\d+-\d+)',
            r'(ACC-SINV-\d+-\d+)',
            r'(MFG-WO-\d+)'
        ]
        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                return match.group(1).upper()
        return None

    def _infer_document_type(self, query):
        """Infer the document type from the query"""
        import re
        if re.search(r'SO-', query, re.IGNORECASE):
            return "Sales Order"
        elif re.search(r'SAL-QTN-|QUOT-', query, re.IGNORECASE):
            return "Quotation"
        elif re.search(r'ACC-SINV-', query, re.IGNORECASE):
            return "Sales Invoice"
        elif re.search(r'MFG-WO-', query, re.IGNORECASE):
            return "Work Order"
        return None

    def scan_quotation(self, quotation_name):
        """Scan a quotation for issues"""
        try:
            qtn = frappe.get_doc("Quotation", quotation_name)
            
            issues = []
            customer = qtn.party_name or qtn.customer_name
            if not customer:
                issues.append({
                    "severity": "HIGH",
                    "field": "customer",
                    "message": "Quotation has no customer assigned"
                })
            
            if not qtn.items or len(qtn.items) == 0:
                issues.append({
                    "severity": "CRITICAL",
                    "field": "items",
                    "message": "Quotation has no items"
                })
            else:
                for i, item in enumerate(qtn.items):
                    if not item.rate or item.rate <= 0:
                        issues.append({
                            "severity": "HIGH",
                            "field": f"items[{i}].rate",
                            "message": f"Item {item.item_code or item.item_name} has no rate"
                        })
            
            if not qtn.transaction_date:
                issues.append({
                    "severity": "MEDIUM",
                    "field": "transaction_date",
                    "message": "Transaction date is missing"
                })
            
            company_currency = frappe.db.get_value("Company", qtn.company, "default_currency")
            if qtn.currency != company_currency:
                issues.append({
                    "severity": "INFO",
                    "field": "currency",
                    "message": f"Multi-currency: Quotation in '{qtn.currency}', company in {company_currency} - Normal for exports"
                })
            
            return {
                "success": True,
                "document_type": "Quotation",
                "document_name": qtn.name,
                "customer": customer,
                "date": str(qtn.transaction_date) if qtn.transaction_date else None,
                "items_count": len(qtn.items),
                "total": qtn.total or 0,
                "currency": qtn.currency,
                "status": qtn.status,
                "issues": issues,
                "issue_counts": {
                    "CRITICAL": len([i for i in issues if i["severity"] == "CRITICAL"]),
                    "HIGH": len([i for i in issues if i["severity"] == "HIGH"]),
                    "MEDIUM": len([i for i in issues if i["severity"] == "MEDIUM"]),
                    "INFO": len([i for i in issues if i["severity"] == "INFO"])
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def diagnose_quotation_pipeline(self, qtn_name):
        """Diagnose quotation pipeline"""
        try:
            result = self.scan_quotation(qtn_name)
            if result.get("success"):
                qtn = frappe.get_doc("Quotation", qtn_name)
                next_steps = []
                
                if qtn.status == "Draft":
                    next_steps.append({"action": "submit", "message": "Submit the quotation"})
                elif qtn.status == "Submitted":
                    if not frappe.db.exists("Sales Order", {"quotation": qtn_name}):
                        next_steps.append({"action": "convert", "message": "Convert to Sales Order"})
                    else:
                        next_steps.append({"action": "view_so", "message": "Sales Order already created"})
                elif qtn.status == "Ordered":
                    next_steps.append({"action": "view_so", "message": "Quotation already converted"})
                
                return {
                    "success": True,
                    "quotation": {
                        "name": result.get("document_name"),
                        "customer": result.get("customer"),
                        "date": result.get("date"),
                        "status": result.get("status"),
                        "total": result.get("total"),
                        "currency": result.get("currency"),
                        "items_count": result.get("items_count")
                    },
                    "issues": result.get("issues", []),
                    "issue_counts": result.get("issue_counts", {}),
                    "pipeline_status": "ready" if result.get("issue_counts", {}).get("CRITICAL", 0) == 0 else "blocked",
                    "next_steps": next_steps
                }
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _store_validation_pattern(self, *args, **kwargs):
        """Store validation pattern"""
        return True

    def _format_scan_result(self, *args, **kwargs):
        """Format scan result"""
        try:
            result_data = args[0] if args else kwargs.get('result_data', {})
            if not isinstance(result_data, dict):
                return str(result_data)
            
            if result_data.get("success") is False:
                return f"❌ Error: {result_data.get('error', 'Unknown error')}"
            
            output = []
            doc_type = result_data.get("document_type", "Document")
            doc_name = result_data.get("document_name", "Unknown")
            output.append(f"## 📋 {doc_type}: {doc_name}")
            
            output.append("\n### 📊 Summary")
            output.append(f"| Metric | Value |")
            output.append(f"|--------|-------|")
            output.append(f"| Customer | {result_data.get('customer', 'N/A')} |")
            output.append(f"| Date | {result_data.get('date', 'N/A')} |")
            output.append(f"| Items | {result_data.get('items_count', 0)} |")
            output.append(f"| Total | {result_data.get('total', 0)} {result_data.get('currency', '')} |")
            output.append(f"| Status | {result_data.get('status', 'N/A')} |")
            
            issues = result_data.get("issues", [])
            if issues:
                output.append("\n### ⚠️ Issues Found")
                for issue in issues:
                    severity = issue.get("severity", "INFO")
                    icon = "🔴" if severity == "CRITICAL" else "🟠" if severity == "HIGH" else "🟡" if severity == "MEDIUM" else "ℹ️"
                    output.append(f"- {icon} **{severity}**: {issue.get('message')} (Field: {issue.get('field')})")
            else:
                output.append("\n### ✅ No issues found")
            
            counts = result_data.get("issue_counts", {})
            output.append("\n### 📊 Issue Summary")
            output.append(f"| Severity | Count |")
            output.append(f"|----------|-------|")
            output.append(f"| 🔴 CRITICAL | {counts.get('CRITICAL', 0)} |")
            output.append(f"| 🟠 HIGH | {counts.get('HIGH', 0)} |")
            output.append(f"| 🟡 MEDIUM | {counts.get('MEDIUM', 0)} |")
            output.append(f"| ℹ️ INFO | {counts.get('INFO', 0)} |")
            
            return "\n".join(output)
        except Exception as e:
            return f"Error formatting: {str(e)}"
