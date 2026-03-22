"""
Command Router - Autonomy + Workflow Command Dispatch
Split from agent.py - Phase 2 Optimization + Phase 3 Quality Management + Phase 4 Analytics

Contains: CommandRouterMixin with autonomy determination and workflow command execution.
"""
import frappe
import re
import urllib.parse
from typing import Optional, Dict


class CommandRouterMixin:
    """
    Mixin that adds command routing and autonomy level determination.
    Requires: self.user
    Expects WorkflowExecutor to be available via raven_ai_agent.api.workflows
    """

    def determine_autonomy(self, query: str) -> int:
        """Karpathy Protocol: Determine appropriate autonomy level"""
        query_lower = query.lower()

        # Level 3 keywords (dangerous operations)
        if any(word in query_lower for word in ["delete", "cancel", "submit", "create invoice", "payment"]):
            return 3

        # Level 2 keywords (modifications/workflow + quality management + analytics)
        if any(word in query_lower for word in ["update", "change", "modify", "set", "add", "convert", "create", "confirm",
                                                  "quality", "calidad", "nc", "capa", "sop", "audit", "training",
                                                  "dashboard", "tablero", "trend", "report", "reporte", "alert", "alerta"]):
            return 2

        # Default to Level 1 (read-only)
        return 1

    def execute_workflow_command(self, query: str, channel_id: str = "", confirm: bool = False) -> Optional[Dict]:
        """Parse and execute workflow commands"""
        frappe.logger().info(f"[Workflow] Checking query: {query}, confirm: {confirm}")

        try:
            from raven_ai_agent.api.workflows import WorkflowExecutor
        except ImportError:
            frappe.logger().info("[Workflow] Workflows disabled")
            return None

        # ---- VALIDATE: Check for full quotation names ----
        # Match full quotation names (like SAL-QTN-2024-0753)
        qtn_match = re.search(r'(SAL-QTN-[\w-]+|QTN-[\w-]+)', query, re.IGNORECASE)
        
        # If validate is called without argument, it will fall through to WorkflowOrchestrator help
        
        executor = WorkflowExecutor(self.user)

        # ---- Confirmation state management (Redis-backed) ----

        # ---- Confirmation state management (Redis-backed) ----
        cache_key = f"pending_confirm:{self.user}:{channel_id}"

        # If confirm parameter is passed (from ! prefix), use it directly
        if confirm:
            is_confirm = True
        else:
            is_confirm = any(word in query_lower for word in ["confirm", "yes", "proceed", "do it", "execute"])

        # If user said "confirm" and we have a pending command, replay it
        if is_confirm and query_lower.strip() in ["confirm", "yes", "proceed", "do it", "execute", "si", "confirmar"]:
            pending_cmd = frappe.cache().get_value(cache_key)
            if pending_cmd:
                frappe.cache().delete_value(cache_key)
                frappe.logger().info(f"[Workflow] Replaying pending command: {pending_cmd}")
                query = pending_cmd
                query_lower = query.lower()
                # is_confirm stays True

        # Force mode with ! prefix (like sudo) - only if confirm param not already set
        is_force = query.startswith("!")
        if is_force and not confirm:
            is_confirm = True
            query = query.lstrip("!").strip()
            query_lower = query.lower()

        # Auto-confirm for privileged users ONLY on explicit confirm words
        if not is_force:
            privileged_roles = ["Sales Manager", "Manufacturing Manager", "Stock Manager", "Accounts Manager", "System Manager"]
            user_roles = frappe.get_roles(self.user)
            if any(role in user_roles for role in privileged_roles):
                pass  # is_confirm stays as-is from keyword check above

        # Quotation patterns
        frappe.logger().info(f"[Workflow] qtn_match: {qtn_match}, 'sales order' in query: {'sales order' in query_lower}")

        # Dry-run mode
        is_dry_run = "--dry-run" in query_lower or "dry run" in query_lower
        if is_dry_run:
            executor.dry_run = True

        # R6: Validate pipeline - handle partial numeric names too
        if "validate" in query_lower or "check pipeline" in query_lower:
            # Check for full quotation names OR partial numeric names (like 0753)
            validate_match = re.search(r'(SAL-QTN-[\w-]+|QTN-[\w-]+|\d{3,5})', query, re.IGNORECASE)
            if validate_match:
                target = validate_match.group(1)
                # If it's numeric-only, resolve it
                if target.isdigit():
                    from raven_ai_agent.utils.doc_resolver import resolve_document_name_safe
                    resolved = resolve_document_name_safe("Quotation", target)
                    if resolved:
                        target = resolved
                
                try:
                    from raven_ai_agent.api.truth_hierarchy import validate_pipeline, format_pipeline_validation
                    result = validate_pipeline(target.upper() if not target.isdigit() else target)
                    return {"success": True, "message": format_pipeline_validation(result)}
                except ImportError:
                    return {"success": False, "error": "Pipeline validation requires truth_hierarchy module."}
                except Exception as e:
                    return {"success": False, "error": f"Validation error: {str(e)}"}
            # If no match but validate is in query, fall through to WorkflowOrchestrator help

        # Complete workflow: Quotation → Invoice
        if qtn_match and "complete" in query_lower and ("workflow" in query_lower or "invoice" in query_lower):
            from raven_ai_agent.api.workflows import complete_workflow_to_invoice
            return complete_workflow_to_invoice(qtn_match.group(1).upper(), dry_run=is_dry_run)

        # Batch migration: multiple quotations
        batch_match = re.findall(r'(SAL-QTN-\d+-\d+)', query, re.IGNORECASE)
        if len(batch_match) > 1 and ("batch" in query_lower or "migrate" in query_lower):
            return executor.batch_migrate_quotations([q.upper() for q in batch_match], dry_run=is_dry_run)

        # Submit quotation
        if qtn_match and "submit" in query_lower and "quotation" in query_lower:
            frappe.logger().info(f"[Workflow] Submitting quotation {qtn_match.group(1)}, confirm={is_confirm}")
            return executor.submit_quotation(qtn_match.group(1).upper(), confirm=is_confirm)

        # Quotation to Sales Order
        if qtn_match and "sales order" in query_lower:
            frappe.logger().info(f"[Workflow] Creating SO from {qtn_match.group(1)}, confirm={is_confirm}")
            return executor.create_sales_order_from_quotation(qtn_match.group(1).upper(), confirm=is_confirm)

        # Sales Order patterns
        # BUG15 fix: Customer names can contain (), commas, etc. that break regex.
        # Strategy: match SO-NNNNN prefix, then resolve full name via DB lookup.
        so_match = re.search(r'(SAL-ORD-\d+-\d+|SO-\d{3,5})', query, re.IGNORECASE)
        if so_match:
            _so_prefix = so_match.group(1).upper()
            # Resolve full SO name from DB (handles special chars in customer names)
            _so_full = frappe.db.get_value("Sales Order",
                {"name": ["like", f"{_so_prefix}%"], "docstatus": ["!=", 2]}, "name")
            if _so_full:
                # Create a match-like object that returns the full name
                class SOMatch:
                    def __init__(self, name):
                        self._name = name
                    def group(self, n=0):
                        return self._name
                so_match = SOMatch(_so_full)
            # else: keep the partial match, let downstream handle the error

        # Submit Sales Order
        if so_match and "submit" in query_lower and "sales order" in query_lower:
            return executor.submit_sales_order(so_match.group(1), confirm=is_confirm)

        # Sales Order to Work Order
        if so_match and "work order" in query_lower:
            return executor.create_work_orders_from_sales_order(so_match.group(1), confirm=is_confirm)

        # Stock Entry for Work Order
        wo_match = re.search(r'(MFG-WO-\d+|LOTE-\d+|P-VTA-\d+|WO-[^\s]+)', query, re.IGNORECASE)
        if wo_match and any(word in query_lower for word in ["stock entry", "material transfer", "manufacture"]):
            return executor.create_stock_entry_for_work_order(wo_match.group(1).upper(), confirm=is_confirm)

        # Delivery Note from Sales Order
        if so_match and any(word in query_lower for word in ["delivery", "ship", "deliver"]):
            return executor.create_delivery_note_from_sales_order(so_match.group(1), confirm=is_confirm)

        # Invoice from DN / SO — now handled by _handle_sales_commands() in
        # sales.py which has full CFDI support: mode_of_payment, debit_to,
        # Banxico FIX rate, mx_product_service_key, party_account_currency,
        # custom posting_date. Falls through to dispatch at ~line 237.

        # Workflow status
        if "workflow status" in query_lower or "track" in query_lower:
            q_match = re.search(r'(SAL-QTN-\d+-\d+)', query, re.IGNORECASE)
            so_match2 = re.search(r'(SAL-ORD-\d+-\d+)', query, re.IGNORECASE)
            return executor.get_workflow_status(
                quotation_name=q_match.group(1).upper() if q_match else None,
                so_name=so_match2.group(1).upper() if so_match2 else None
            )

        # Submit BOM: first try standard BOM doctype, then BOM Creator
        if "submit" in query_lower and "bom" in query_lower:
            bom_match = re.search(r'(BOM-[^\s]+)', query, re.IGNORECASE)
            if bom_match:
                bom_name = urllib.parse.unquote(bom_match.group(1))

                # Try standard BOM first
                if frappe.db.exists("BOM", bom_name):
                    try:
                        bom_doc = frappe.get_doc("BOM", bom_name)
                        if bom_doc.docstatus == 0:  # Draft
                            bom_doc.submit()
                            return {
                                "success": True,
                                "message": f"✅ BOM '{bom_name}' submitted successfully!\n\n"
                                           f"  Item: {bom_doc.item}\n"
                                           f"  Qty: {bom_doc.quantity} {bom_doc.uom}\n"
                                           f"  Items: {len(bom_doc.items)}\n"
                                           f"  Status: Submitted"
                            }
                        elif bom_doc.docstatus == 1:
                            return {"success": False, "error": f"BOM '{bom_name}' is already submitted."}
                        else:
                            return {"success": False, "error": f"BOM '{bom_name}' is cancelled (docstatus=2). Cannot submit."}
                    except Exception as e:
                        return {"success": False, "error": f"Error submitting BOM '{bom_name}': {str(e)}"}

                # Fallback: try BOM Creator
                try:
                    from raven_ai_agent.agents.bom_creator_agent import submit_bom_creator
                    result = submit_bom_creator(bom_name)
                    if result.get("success"):
                        return {
                            "success": True,
                            "message": result.get("message", f"✅ BOM Creator '{bom_name}' submitted successfully!")
                        }
                    else:
                        return {
                            "success": False,
                            "error": result.get("error", f"'{bom_name}' not found as BOM or BOM Creator.")
                        }
                except Exception as e:
                    return {"success": False, "error": f"'{bom_name}' not found as standard BOM, and BOM Creator lookup failed: {str(e)}"}

        # Create BOM for Batch: @ai create bom for batch LOTE-XXXX
        if "create bom" in query_lower and ("batch" in query_lower or "lote" in query_lower):
            batch_match = re.search(r'(LOTE-[^\s]+)', query, re.IGNORECASE)
            if not batch_match:
                batch_match = re.search(r'(?:batch|lote)\s+([^\s]+)', query, re.IGNORECASE)

            if batch_match:
                batch_name = batch_match.group(1).upper()
                try:
                    from raven_ai_agent.agents.bom_creator_agent import create_bom_for_batch
                    result = create_bom_for_batch(batch_name)
                    if result.get("success"):
                        return {
                            "success": True,
                            "message": result.get("message", f"✅ BOM created for batch '{batch_name}'")
                        }
                    else:
                        return {
                            "success": False,
                            "error": result.get("error", "Failed to create BOM for batch")
                        }
                except Exception as e:
                    return {"success": False, "error": f"Error creating BOM for batch: {str(e)}"}
            else:
                return {"success": False, "error": "Please specify batch name: '@ai create bom for batch LOTE-XXXX'"}

        # === DISPATCH TO HANDLER MODULES ===
        # Manufacturing SOP
        result = self._handle_manufacturing_commands(query, query_lower, is_confirm=is_confirm)
        if result is not None:
            return result

        # BOM Commands
        result = self._handle_bom_commands(query, query_lower, is_confirm=is_confirm)
        if result is not None:
            return result

        # Direct Web Search
        result = self._handle_web_search_commands(query, query_lower)
        if result is not None:
            return result

        # Sales-to-Purchase Cycle (pass is_confirm for ! commands)
        result = self._handle_sales_commands(query, query_lower, is_confirm=is_confirm)
        if result is not None:
            return result

        # Quotation Management
        result = self._handle_quotation_commands(query, query_lower, is_confirm=is_confirm)
        if result is not None:
            return result

        # Phase 3: Quality Management System
        result = self._handle_quality_commands(query, query_lower, is_confirm=is_confirm)
        if result is not None:
            return result

        # Phase 4: Analytics & Reporting
        result = self._handle_analytics_commands(query, query_lower, is_confirm=is_confirm)
        if result is not None:
            return result

        return None
