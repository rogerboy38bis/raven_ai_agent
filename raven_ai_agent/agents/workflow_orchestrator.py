"""
Workflow Orchestrator Agent
Master orchestrator that chains all 8 steps of the verified workflow:

  Step 1: WO (Manufacturing) → Submit
  Step 2: Stock Entry (Manufacture)
  Step 3: SO → Submit
  Step 4: Sales WO (Work Order from SO)
  Step 5: Stock Entry (Manufacture for Sales)
  Step 6: Delivery Note
  Step 7: Sales Invoice
  Step 8: Payment Entry

Handles:
  - Full cycle: Quotation → SO → WO → SE → DN → SI → PE
  - Item 0307 vs ITEM_0612 mapping (manufactured item matches SO item)
  - CFDI compliance: auto-set mx_cfdi_use to G03, custom_customer_invoice_currency
  - Status dashboard showing pipeline position
  - No import frappe in Server Scripts

Author: raven_ai_agent
"""
import frappe
import re
from typing import Dict, List, Optional
from frappe.utils import nowdate, getdate, flt, add_days
from raven_ai_agent.utils.doc_resolver import resolve_document_name_safe


class WorkflowOrchestrator:
    """Master orchestrator for the 8-step manufacturing-to-payment workflow"""

    PIPELINE_STEPS = [
        {"step": 1, "name": "Manufacturing WO", "doctype": "Work Order", "description": "Create & submit manufacturing Work Order"},
        {"step": 2, "name": "Stock Entry (Manufacture)", "doctype": "Stock Entry", "description": "Manufacture from WO → FG to stock"},
        {"step": 3, "name": "Sales Order", "doctype": "Sales Order", "description": "Submit Sales Order"},
        {"step": 4, "name": "Sales WO", "doctype": "Work Order", "description": "Create WO from SO (labeling)"},
        {"step": 5, "name": "Stock Entry (Sales)", "doctype": "Stock Entry", "description": "Manufacture for Sales WO"},
        {"step": 6, "name": "Delivery Note", "doctype": "Delivery Note", "description": "Create DN from SO"},
        {"step": 7, "name": "Sales Invoice", "doctype": "Sales Invoice", "description": "Create SI from SO/DN"},
        {"step": 8, "name": "Payment Entry", "doctype": "Payment Entry", "description": "Create PE from SI"},
    ]

    def __init__(self, user: str = None):
        self.user = user or frappe.session.user
        self.site_name = frappe.local.site

    def make_link(self, doctype: str, name: str) -> str:
        """Generate clickable markdown link"""
        slug = doctype.lower().replace(" ", "-")
        return f"[{name}](https://{self.site_name}/app/{slug}/{name})"

    # ========== FULL CYCLE EXECUTION ==========

    def run_full_cycle(self, so_name: str, mfg_bom: str = None,
                       sales_bom: str = None, skip_steps: List[int] = None) -> Dict:
        """Execute the complete 8-step workflow for a Sales Order.
        
        This is the master function that chains all steps. It validates
        prerequisites at each step and stops on errors.
        
        Args:
            so_name: Sales Order name (e.g. 'SO-00752-LEGOSAN AB')
            mfg_bom: Manufacturing BOM (e.g. 'BOM-0307-005' — Mix level)
            sales_bom: Sales BOM (e.g. 'BOM-0307-001' — Sales level with label)
            skip_steps: List of step numbers to skip (e.g. [1, 2] if manufacturing already done)
        
        Returns:
            Dict with step-by-step results
        """
        skip_steps = skip_steps or []
        results = []
        pipeline_state = {"so_name": so_name, "errors": []}

        try:
            # Resolve partial SO name to full name (e.g., "SO-00752" → "SO-00752-LEGOSAN AB")
            resolved_so = resolve_document_name_safe("Sales Order", so_name)
            if resolved_so:
                so_name = resolved_so
            
            so = frappe.get_doc("Sales Order", so_name)
        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Sales Order '{so_name}' not found."}

        item = so.items[0] if so.items else None
        if not item:
            return {"success": False, "error": f"Sales Order '{so_name}' has no items."}

        item_code = item.item_code
        qty = item.qty

        # Resolve BOMs
        if not sales_bom:
            sales_bom = frappe.db.get_value("BOM",
                {"item": item_code, "is_active": 1, "is_default": 1, "docstatus": 1}, "name")
        if not mfg_bom:
            # Look for a non-default active BOM (the mix/production BOM)
            mfg_bom = frappe.db.get_value("BOM",
                {"item": item_code, "is_active": 1, "is_default": 0, "docstatus": 1}, "name")

        # ---- Step 1: Manufacturing Work Order ----
        if 1 not in skip_steps:
            step_result = self._step_1_create_mfg_wo(item_code, qty, mfg_bom, so)
            results.append(step_result)
            if not step_result["success"]:
                pipeline_state["errors"].append(step_result)
                return self._build_pipeline_response(results, pipeline_state)
            pipeline_state["mfg_wo"] = step_result.get("wo_name")
        else:
            results.append({"step": 1, "skipped": True, "success": True})

        # ---- Step 2: Stock Entry (Manufacture) ----
        if 2 not in skip_steps and pipeline_state.get("mfg_wo"):
            step_result = self._step_2_manufacture(pipeline_state["mfg_wo"])
            results.append(step_result)
            if not step_result["success"]:
                pipeline_state["errors"].append(step_result)
                return self._build_pipeline_response(results, pipeline_state)
            pipeline_state["mfg_se"] = step_result.get("se_name")
        else:
            results.append({"step": 2, "skipped": True, "success": True})

        # ---- Step 3: Submit Sales Order ----
        if 3 not in skip_steps:
            step_result = self._step_3_submit_so(so)
            results.append(step_result)
            if not step_result["success"]:
                pipeline_state["errors"].append(step_result)
                return self._build_pipeline_response(results, pipeline_state)
        else:
            results.append({"step": 3, "skipped": True, "success": True})

        # ---- Step 4: Sales Work Order ----
        if 4 not in skip_steps:
            step_result = self._step_4_create_sales_wo(item_code, qty, sales_bom, so)
            results.append(step_result)
            if not step_result["success"]:
                pipeline_state["errors"].append(step_result)
                return self._build_pipeline_response(results, pipeline_state)
            pipeline_state["sales_wo"] = step_result.get("wo_name")
        else:
            results.append({"step": 4, "skipped": True, "success": True})

        # ---- Step 5: Stock Entry (Manufacture for Sales) ----
        if 5 not in skip_steps and pipeline_state.get("sales_wo"):
            step_result = self._step_5_manufacture_sales(pipeline_state["sales_wo"])
            results.append(step_result)
            if not step_result["success"]:
                pipeline_state["errors"].append(step_result)
                return self._build_pipeline_response(results, pipeline_state)
            pipeline_state["sales_se"] = step_result.get("se_name")
        else:
            results.append({"step": 5, "skipped": True, "success": True})

        # ---- Step 6: Delivery Note ----
        if 6 not in skip_steps:
            step_result = self._step_6_delivery_note(so)
            results.append(step_result)
            if not step_result["success"]:
                pipeline_state["errors"].append(step_result)
                return self._build_pipeline_response(results, pipeline_state)
            pipeline_state["dn"] = step_result.get("dn_name")
        else:
            results.append({"step": 6, "skipped": True, "success": True})

        # ---- Step 7: Sales Invoice ----
        if 7 not in skip_steps:
            step_result = self._step_7_sales_invoice(so, pipeline_state.get("dn"))
            results.append(step_result)
            if not step_result["success"]:
                pipeline_state["errors"].append(step_result)
                return self._build_pipeline_response(results, pipeline_state)
            pipeline_state["si"] = step_result.get("si_name")
        else:
            results.append({"step": 7, "skipped": True, "success": True})

        # ---- Step 8: Payment Entry ----
        if 8 not in skip_steps and pipeline_state.get("si"):
            step_result = self._step_8_payment_entry(pipeline_state["si"])
            results.append(step_result)
            if not step_result["success"]:
                pipeline_state["errors"].append(step_result)
            pipeline_state["pe"] = step_result.get("pe_name")
        else:
            results.append({"step": 8, "skipped": True, "success": True})

        return self._build_pipeline_response(results, pipeline_state)

    # ========== INDIVIDUAL STEP IMPLEMENTATIONS ==========

    def _step_1_create_mfg_wo(self, item_code, qty, mfg_bom, so) -> Dict:
        """Step 1: Create manufacturing Work Order"""
        try:
            if not mfg_bom:
                return {"step": 1, "success": False, "error": f"No manufacturing BOM found for '{item_code}'"}

            from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
            mfg = ManufacturingAgent(self.user)
            result = mfg.create_work_order(
                item_code=item_code,
                qty=qty,
                bom=mfg_bom,
                project=so.project if hasattr(so, "project") else None,
                use_multi_level_bom=0
            )
            result["step"] = 1
            return result
        except Exception as e:
            return {"step": 1, "success": False, "error": str(e)}

    def _step_2_manufacture(self, wo_name) -> Dict:
        """Step 2: Submit WO + Material Transfer + Manufacture"""
        try:
            from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
            mfg = ManufacturingAgent(self.user)

            # Submit WO first
            submit_result = mfg.submit_work_order(wo_name)
            if not submit_result["success"]:
                # Already submitted is OK
                if "already submitted" not in submit_result.get("message", ""):
                    return {"step": 2, "success": False, "error": submit_result.get("error", "Submit failed")}

            # Transfer materials
            transfer_result = mfg.create_material_transfer(wo_name)
            # Transfer might already be done — that's OK

            # Create manufacture stock entry
            result = mfg.create_stock_entry_manufacture(wo_name)
            result["step"] = 2
            return result
        except Exception as e:
            return {"step": 2, "success": False, "error": str(e)}

    def _step_3_submit_so(self, so) -> Dict:
        """Step 3: Submit Sales Order if not already submitted"""
        try:
            if so.docstatus == 1:
                return {
                    "step": 3, "success": True,
                    "message": f"✅ Sales Order {self.make_link('Sales Order', so.name)} already submitted."
                }
            if so.docstatus == 2:
                return {"step": 3, "success": False, "error": f"Sales Order {so.name} is cancelled."}

            so.submit()
            frappe.db.commit()
            return {
                "step": 3, "success": True,
                "message": f"✅ Sales Order submitted: {self.make_link('Sales Order', so.name)}"
            }
        except Exception as e:
            return {"step": 3, "success": False, "error": str(e)}

    def _step_4_create_sales_wo(self, item_code, qty, sales_bom, so) -> Dict:
        """Step 4: Create Sales Work Order from SO (labeling step)"""
        try:
            if not sales_bom:
                return {"step": 4, "success": False, "error": f"No sales BOM found for '{item_code}'"}

            from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
            mfg = ManufacturingAgent(self.user)
            result = mfg.create_work_order(
                item_code=item_code,
                qty=qty,
                bom=sales_bom,
                sales_order=so.name,
                project=so.project if hasattr(so, "project") else None,
                use_multi_level_bom=0
            )
            result["step"] = 4
            return result
        except Exception as e:
            return {"step": 4, "success": False, "error": str(e)}

    def _step_5_manufacture_sales(self, wo_name) -> Dict:
        """Step 5: Submit + Manufacture for sales WO (labeling)"""
        try:
            from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
            mfg = ManufacturingAgent(self.user)

            submit_result = mfg.submit_work_order(wo_name)
            transfer_result = mfg.create_material_transfer(wo_name)
            result = mfg.create_stock_entry_manufacture(wo_name)
            result["step"] = 5
            return result
        except Exception as e:
            return {"step": 5, "success": False, "error": str(e)}

    def _step_6_delivery_note(self, so) -> Dict:
        """Step 6: Create Delivery Note from Sales Order"""
        try:
            # R2: Idempotency guard — check for existing DN
            try:
                from raven_ai_agent.api.truth_hierarchy import check_existing_dn
                existing_dn = check_existing_dn(so.name)
                if existing_dn:
                    return {
                        "step": 6, "success": True,
                        "dn_name": existing_dn,
                        "link": self.make_link("Delivery Note", existing_dn),
                        "message": f"✅ Delivery Note {self.make_link('Delivery Note', existing_dn)} already exists for {so.name}"
                    }
            except ImportError:
                pass  # truth_hierarchy not available, skip guard

            # Check inventory first
            for item in so.items:
                available = frappe.db.get_value("Bin",
                    {"item_code": item.item_code, "warehouse": item.warehouse},
                    "actual_qty") or 0
                if flt(available) < flt(item.qty):
                    return {
                        "step": 6, "success": False,
                        "error": (
                            f"Insufficient stock for {item.item_code}: "
                            f"need {item.qty}, have {available} in {item.warehouse}. "
                            f"Complete manufacturing first."
                        )
                    }

            from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note
            dn = make_delivery_note(so.name)
            dn.insert(ignore_permissions=True)
            dn.submit()
            frappe.db.commit()

            return {
                "step": 6, "success": True,
                "dn_name": dn.name,
                "link": self.make_link("Delivery Note", dn.name),
                "message": (
                    f"✅ Delivery Note created: {self.make_link('Delivery Note', dn.name)}\n"
                    f"  Customer: {so.customer}\n"
                    f"  Items: {len(dn.items)}"
                )
            }
        except Exception as e:
            return {"step": 6, "success": False, "error": str(e)}

    def _step_7_sales_invoice(self, so, dn_name: str = None) -> Dict:
        """Step 7: Create Sales Invoice from SO/DN with CFDI compliance"""
        try:
            # R2: Idempotency guard — check for existing SI
            try:
                from raven_ai_agent.api.truth_hierarchy import check_existing_si, resolve_mx_cfdi_fields
                existing_si = check_existing_si(so_name=so.name, dn_name=dn_name)
                if existing_si:
                    return {
                        "step": 7, "success": True,
                        "si_name": existing_si,
                        "link": self.make_link("Sales Invoice", existing_si),
                        "message": f"✅ Sales Invoice {self.make_link('Sales Invoice', existing_si)} already exists for {so.name}"
                    }
            except ImportError:
                pass  # truth_hierarchy not available, skip guard

            if dn_name:
                from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice
                si = make_sales_invoice(dn_name)
            else:
                from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
                si = make_sales_invoice(so.name)

            # R1+R7: CFDI compliance via truth hierarchy (replaces hardcoded G03)
            try:
                cfdi = resolve_mx_cfdi_fields(source_doc=so)
                if hasattr(si, 'mx_payment_option'):
                    si.mx_payment_option = cfdi['mx_payment_option']
                if hasattr(si, 'mx_cfdi_use'):
                    si.mx_cfdi_use = cfdi['mx_cfdi_use']
                if hasattr(si, 'mode_of_payment'):
                    si.mode_of_payment = cfdi['mode_of_payment']
                # Log audit trail
                audit_msg = ' | '.join(
                    f"{d['field']}={d['value']} ({d['tier_label']})"
                    for d in cfdi.get('_audit', [])
                )
                frappe.logger('raven_ai_agent').info(
                    f"SI for {so.name}: {audit_msg}"
                )
            except ImportError:
                # Fallback: old behavior if truth_hierarchy not available
                if hasattr(si, 'mx_cfdi_use'):
                    si.mx_cfdi_use = 'G03'
            
            if hasattr(si, "custom_customer_invoice_currency"):
                si.custom_customer_invoice_currency = so.currency

            si.insert(ignore_permissions=True)
            si.submit()
            frappe.db.commit()

            return {
                "step": 7, "success": True,
                "si_name": si.name,
                "link": self.make_link("Sales Invoice", si.name),
                "message": (
                    f"✅ Sales Invoice created: {self.make_link('Sales Invoice', si.name)}\n"
                    f"  Customer: {so.customer}\n"
                    f"  Grand Total: {si.grand_total} {si.currency}\n"
                    f"  CFDI Use: {getattr(si, 'mx_cfdi_use', 'N/A')}"
                )
            }
        except Exception as e:
            return {"step": 7, "success": False, "error": str(e)}

    def _step_8_payment_entry(self, si_name: str) -> Dict:
        """Step 8: Create Payment Entry from Sales Invoice"""
        try:
            from raven_ai_agent.agents.payment_agent import PaymentAgent
            payment = PaymentAgent(self.user)
            result = payment.create_payment_entry(si_name)
            result["step"] = 8
            return result
        except Exception as e:
            return {"step": 8, "success": False, "error": str(e)}

    # ========== STATUS DASHBOARD ==========

    def get_pipeline_status(self, so_name: str) -> Dict:
        """Show where a Sales Order is in the 8-step pipeline.
        
        Args:
            so_name: Sales Order name
        
        Returns:
            Dict with pipeline position and status of each step
        """
        try:
            # Resolve partial SO name to full name
            resolved_so = resolve_document_name_safe("Sales Order", so_name)
            if resolved_so:
                so_name = resolved_so
            
            so = frappe.get_doc("Sales Order", so_name)
            item_code = so.items[0].item_code if so.items else None

            dashboard = []

            # Step 1 & 2: Check Work Orders (manufacturing)
            work_orders = frappe.get_all("Work Order",
                filters={"production_item": item_code, "docstatus": ["!=", 2]},
                fields=["name", "bom_no", "status", "qty", "produced_qty", "sales_order"],
                order_by="creation asc")

            mfg_wos = [w for w in work_orders if not w.sales_order]
            sales_wos = [w for w in work_orders if w.sales_order == so_name]

            # Step 1: Manufacturing WO
            if mfg_wos:
                wo = mfg_wos[-1]
                dashboard.append({
                    "step": 1, "name": "Manufacturing WO",
                    "status": wo.status,
                    "doc": self.make_link("Work Order", wo.name),
                    "complete": wo.status in ["Completed", "In Process"]
                })
            else:
                dashboard.append({"step": 1, "name": "Manufacturing WO", "status": "Not Created", "complete": False})

            # Step 2: Stock Entry (Manufacture)
            mfg_ses = []
            for wo in mfg_wos:
                ses = frappe.get_all("Stock Entry",
                    filters={"work_order": wo.name, "stock_entry_type": "Manufacture", "docstatus": 1},
                    fields=["name"])
                mfg_ses.extend(ses)

            if mfg_ses:
                dashboard.append({
                    "step": 2, "name": "Stock Entry (Manufacture)",
                    "status": "Completed",
                    "doc": self.make_link("Stock Entry", mfg_ses[-1].name),
                    "complete": True
                })
            else:
                dashboard.append({"step": 2, "name": "Stock Entry (Manufacture)", "status": "Pending", "complete": False})

            # Step 3: Sales Order
            dashboard.append({
                "step": 3, "name": "Sales Order",
                "status": so.status,
                "doc": self.make_link("Sales Order", so.name),
                "complete": so.docstatus == 1
            })

            # Step 4: Sales WO
            if sales_wos:
                swo = sales_wos[-1]
                dashboard.append({
                    "step": 4, "name": "Sales WO",
                    "status": swo.status,
                    "doc": self.make_link("Work Order", swo.name),
                    "complete": swo.status in ["Completed", "In Process"]
                })
            else:
                dashboard.append({"step": 4, "name": "Sales WO", "status": "Not Created", "complete": False})

            # Step 5: Stock Entry (Sales Manufacture)
            sales_ses = []
            for swo in sales_wos:
                ses = frappe.get_all("Stock Entry",
                    filters={"work_order": swo.name, "stock_entry_type": "Manufacture", "docstatus": 1},
                    fields=["name"])
                sales_ses.extend(ses)

            if sales_ses:
                dashboard.append({
                    "step": 5, "name": "Stock Entry (Sales)",
                    "status": "Completed",
                    "doc": self.make_link("Stock Entry", sales_ses[-1].name),
                    "complete": True
                })
            else:
                dashboard.append({"step": 5, "name": "Stock Entry (Sales)", "status": "Pending", "complete": False})

            # Step 6: Delivery Note
            dns = frappe.get_all("Delivery Note Item",
                filters={"against_sales_order": so_name, "docstatus": ["!=", 2]},
                fields=["parent"], distinct=True)
            if dns:
                dn_name = dns[-1].parent
                dn_status = frappe.db.get_value("Delivery Note", dn_name, "docstatus")
                dashboard.append({
                    "step": 6, "name": "Delivery Note",
                    "status": "Submitted" if dn_status == 1 else "Draft",
                    "doc": self.make_link("Delivery Note", dn_name),
                    "complete": dn_status == 1
                })
            else:
                dashboard.append({"step": 6, "name": "Delivery Note", "status": "Not Created", "complete": False})

            # Step 7: Sales Invoice
            sis = frappe.get_all("Sales Invoice Item",
                filters={"sales_order": so_name, "docstatus": ["!=", 2]},
                fields=["parent"], distinct=True)
            if sis:
                si_name = sis[-1].parent
                si_doc = frappe.get_doc("Sales Invoice", si_name)
                dashboard.append({
                    "step": 7, "name": "Sales Invoice",
                    "status": f"{'Submitted' if si_doc.docstatus == 1 else 'Draft'} (Outstanding: {si_doc.outstanding_amount})",
                    "doc": self.make_link("Sales Invoice", si_name),
                    "complete": si_doc.docstatus == 1
                })
            else:
                dashboard.append({"step": 7, "name": "Sales Invoice", "status": "Not Created", "complete": False})

            # Step 8: Payment Entry
            if sis:
                pes = frappe.get_all("Payment Entry Reference",
                    filters={"reference_doctype": "Sales Invoice", "reference_name": sis[-1].parent, "docstatus": ["!=", 2]},
                    fields=["parent"], distinct=True)
                if pes:
                    pe_name = pes[-1].parent
                    pe_status = frappe.db.get_value("Payment Entry", pe_name, "docstatus")
                    dashboard.append({
                        "step": 8, "name": "Payment Entry",
                        "status": "Submitted" if pe_status == 1 else "Draft",
                        "doc": self.make_link("Payment Entry", pe_name),
                        "complete": pe_status == 1
                    })
                else:
                    dashboard.append({"step": 8, "name": "Payment Entry", "status": "Not Created", "complete": False})
            else:
                dashboard.append({"step": 8, "name": "Payment Entry", "status": "Pending (no invoice)", "complete": False})

            # Build visual dashboard
            completed_steps = sum(1 for d in dashboard if d["complete"])
            progress_pct = int((completed_steps / 8) * 100)

            msg = (
                f"📊 **Pipeline Dashboard for {self.make_link('Sales Order', so_name)}**\n\n"
                f"  Customer: {so.customer}\n"
                f"  Item: {item_code} | Qty: {so.items[0].qty if so.items else 'N/A'}\n"
                f"  Progress: **{completed_steps}/8 steps** ({progress_pct}%)\n\n"
                f"| Step | Stage | Status | Document |\n"
                f"|------|-------|--------|----------|\n"
            )
            for d in dashboard:
                icon = "✅" if d["complete"] else "⏳"
                doc_link = d.get("doc", "—")
                msg += f"| {icon} {d['step']} | {d['name']} | {d['status']} | {doc_link} |\n"

            # Identify next action
            for d in dashboard:
                if not d["complete"]:
                    msg += f"\n➡️ **Next action:** Step {d['step']} — {d['name']} ({d['status']})"
                    break
            else:
                msg += "\n🎉 **Pipeline complete!**"

            return {"success": True, "dashboard": dashboard, "progress": progress_pct, "message": msg}

        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Sales Order '{so_name}' not found."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def create_so_from_quotation(self, quotation_name: str) -> Dict:
        """Create a Sales Order from a Quotation (pre-Step 3).
        
        Args:
            quotation_name: Quotation name (e.g. 'SAL-QTN-2024-00752')
        
        Returns:
            Dict with created SO details
        """
        try:
            qt = frappe.get_doc("Quotation", quotation_name)

            if qt.docstatus != 1:
                return {"success": False, "error": f"Quotation '{quotation_name}' must be submitted first."}

            # R2: Idempotency guard — check for existing SO
            try:
                from raven_ai_agent.api.truth_hierarchy import check_existing_so
                existing_so = check_existing_so(quotation_name)
                if existing_so:
                    return {
                        "success": True,
                        "so_name": existing_so,
                        "link": self.make_link("Sales Order", existing_so),
                        "message": f"✅ Sales Order {self.make_link('Sales Order', existing_so)} already exists for {quotation_name}"
                    }
            except ImportError:
                pass

            if qt.status == "Ordered":
                return {
                    "success": True,
                    "message": f"✅ Quotation {self.make_link('Quotation', quotation_name)} is already ordered."
                }

            from erpnext.selling.doctype.quotation.quotation import make_sales_order
            so = make_sales_order(quotation_name)
            
            # BUG18 fix: Recalculate payment_schedule due_dates relative to today
            # Old QTNs carry stale due_date from original transaction (e.g. 2026-02-02)
            # ERPNext v16 rejects "Due Date cannot be before Posting Date"
            today = nowdate()
            so.transaction_date = today
            so.delivery_date = add_days(today, 30)
            if hasattr(so, 'payment_schedule') and so.payment_schedule:
                for ps_row in so.payment_schedule:
                    credit_days = int(ps_row.credit_days or 0)
                    ps_row.due_date = add_days(today, credit_days)
            
            so.insert(ignore_permissions=True)
            frappe.db.commit()

            return {
                "success": True,
                "so_name": so.name,
                "link": self.make_link("Sales Order", so.name),
                "message": (
                    f"✅ Sales Order created from Quotation:\n\n"
                    f"  Quotation: {self.make_link('Quotation', quotation_name)}\n"
                    f"  Sales Order: {self.make_link('Sales Order', so.name)}\n"
                    f"  Customer: {so.customer}\n"
                    f"  Grand Total: {so.grand_total} {so.currency}"
                )
            }
        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Quotation '{quotation_name}' not found."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ========== MAIN COMMAND HANDLER ==========

    def process_command(self, message: str) -> str:
        """Process incoming Raven command and return formatted response.
        
        Commands:
            @workflow run [SO-NAME]
            @workflow run [SO-NAME] mfg-bom [BOM] sales-bom [BOM]
            @workflow run [SO-NAME] skip [1,2]
            @workflow status [SO-NAME]
            @workflow create so from [QTN-NAME]
            @workflow help
        """
        message_lower = message.lower().strip()

        # ---- PARSE SUBCOMMAND ----
        # Extract the first word (after @workflow was stripped by agent.py)
        # Message is now like "validate 0753" or "run SO-00752" or "help"
        parts = message.split()
        subcommand = parts[0].lower() if parts else ""
        
        # Get everything after the subcommand
        subcommand_arg = " ".join(parts[1:]).strip() if len(parts) > 1 else ""

        # Extract document names
        so_pattern = r'(SO-[\w-]+(?:\s+(?!from\b|to\b|pipeline\b|status\b|check\b|audit\b|validate\b|diagnose\b|bom\b|qty\b|quantity\b|item\b|warehouse\b|wh\b)[\w\.]+)*|SAL-ORD-[\d-]+)'
        so_match = re.search(so_pattern, message, re.IGNORECASE)
        so_name = so_match.group(1) if so_match else None

        qtn_pattern = r'(SAL-QTN-[\w-]+|QTN-[\w-]+)'
        qtn_match = re.search(qtn_pattern, message, re.IGNORECASE)
        qtn_name = qtn_match.group(1) if qtn_match else None
        
        # Also check for numeric-only names like 0753
        numeric_match = re.search(r'(\d{3,5})', message, re.IGNORECASE)
        numeric_name = numeric_match.group(1) if numeric_match else None

        # ---- HELP ----
        if "help" in message_lower or "capabilities" in message_lower:
            return self._help_text()

        # ---- RUN FULL CYCLE ----
        if "run" in message_lower and so_name:
            mfg_bom_match = re.search(r'mfg[_-]?bom\s+(BOM-[\w-]+)', message, re.IGNORECASE)
            sales_bom_match = re.search(r'sales[_-]?bom\s+(BOM-[\w-]+)', message, re.IGNORECASE)
            skip_match = re.search(r'skip\s+\[?([\d,\s]+)\]?', message, re.IGNORECASE)

            mfg_bom = mfg_bom_match.group(1) if mfg_bom_match else None
            sales_bom = sales_bom_match.group(1) if sales_bom_match else None
            skip_steps = [int(s.strip()) for s in skip_match.group(1).split(",")] if skip_match else None

            result = self.run_full_cycle(so_name, mfg_bom=mfg_bom,
                                         sales_bom=sales_bom, skip_steps=skip_steps)
            return result.get("message", result.get("error", "Unknown error"))

        # ---- PIPELINE STATUS ----
        if ("status" in message_lower or "dashboard" in message_lower
                or "pipeline" in message_lower) and so_name:
            # Resolve partial SO name to full name
            resolved_so = resolve_document_name_safe("Sales Order", so_name)
            if resolved_so:
                so_name = resolved_so
            result = self.get_pipeline_status(so_name)
            return result.get("message", result.get("error", "Unknown error"))

        # ---- VALIDATE PIPELINE (R6) ----
        if subcommand == "validate":
            # Case A: No argument - show mini-help
            if not subcommand_arg:
                return (
                    "❓ **Usage:** @workflow validate <Quotation or Sales Order>\n\n"
                    "**Examples:**\n"
                    "- @workflow validate SAL-QTN-2024-00752\n"
                    "- @workflow validate SAL-QTN-2024-0753\n"
                    "- @workflow validate SO-00752\n\n"
                    "**Partial names supported:**\n"
                    "- 0753 → SAL-QTN-2024-00753\n"
                    "- SO-00752 → SO-00752-LEGOSAN AB\n\n"
                    "The system will auto-resolve partial / mistyped names."
                )
            
            # Case B: Argument present - run validation
            # Use qtn_name if found, otherwise try numeric_name
            target = qtn_name if qtn_name else (numeric_name if numeric_name else subcommand_arg)
            
            # Resolve partial/mistyped names
            resolved = resolve_document_name_safe("Quotation", target)
            if resolved:
                target = resolved
            
            try:
                from raven_ai_agent.api.truth_hierarchy import validate_pipeline, format_pipeline_validation
                result = validate_pipeline(target)
                return format_pipeline_validation(result)
            except ImportError:
                return "Pipeline validation requires truth_hierarchy module."
            except Exception as e:
                return f"Validation error: {str(e)}"

        # ---- CREATE SO FROM QUOTATION ----
        if "create" in message_lower and "so" in message_lower and qtn_name:
            # Resolve partial Quotation name to full name
            resolved_qtn = resolve_document_name_safe("Quotation", qtn_name)
            if resolved_qtn:
                qtn_name = resolved_qtn
                
            result = self.create_so_from_quotation(qtn_name)
            return result.get("message", result.get("error", "Unknown error"))

        # ---- FALLBACK ----
        return self._help_text()

    def _build_pipeline_response(self, results: List[Dict], state: Dict) -> Dict:
        """Build formatted response from pipeline execution results"""
        completed = [r for r in results if r.get("success")]
        failed = [r for r in results if not r.get("success") and not r.get("skipped")]
        skipped = [r for r in results if r.get("skipped")]

        msg = f"🔄 **Workflow Execution for {self.make_link('Sales Order', state['so_name'])}**\n\n"

        for r in results:
            step = r.get("step", "?")
            if r.get("skipped"):
                msg += f"⏭️ Step {step}: Skipped\n"
            elif r.get("success"):
                msg += f"✅ Step {step}: {r.get('message', 'OK')[:80]}\n"
            else:
                msg += f"❌ Step {step}: {r.get('error', 'Failed')[:80]}\n"

        msg += f"\n📊 Completed: {len(completed)} | Failed: {len(failed)} | Skipped: {len(skipped)}"

        success = len(failed) == 0
        return {"success": success, "results": results, "state": state, "message": msg}

    def _help_text(self) -> str:
        return (
            "🔄 **Workflow Orchestrator — Commands**\n\n"
            "**Full Cycle**\n"
            "`@workflow run [SO-NAME]` — Execute all 8 steps\n"
            "`@workflow run [SO-NAME] mfg-bom [BOM] sales-bom [BOM]` — With specific BOMs\n"
            "`@workflow run [SO-NAME] skip [1,2]` — Skip completed steps\n\n"
            "**Status**\n"
            "`@workflow status [SO-NAME]` — Pipeline dashboard\n"
            "`@workflow dashboard [SO-NAME]` — Same as status\n\n"
            "**Pre-workflow**\n"
            "`@workflow create so from [QTN-NAME]` — Create SO from Quotation\n"
            "`@workflow validate [QTN-NAME]` — Validate full pipeline (R6)\n\n"
            "**The 8 Steps:**\n"
            "```\n"
            "1. Manufacturing WO (create + submit)\n"
            "2. Stock Entry — Manufacture\n"
            "3. Sales Order — Submit\n"
            "4. Sales WO (from SO, labeling)\n"
            "5. Stock Entry — Manufacture (Sales)\n"
            "6. Delivery Note\n"
            "7. Sales Invoice (CFDI G03)\n"
            "8. Payment Entry\n"
            "```\n\n"
            "**Example**\n"
            "```\n"
            "@workflow run SO-00752-LEGOSAN AB mfg-bom BOM-0307-005 sales-bom BOM-0307-001\n"
            "@workflow status SO-00752-LEGOSAN AB\n"
            "```"
        )
