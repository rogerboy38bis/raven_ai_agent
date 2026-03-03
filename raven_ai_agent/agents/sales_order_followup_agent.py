"""
Sales Order Follow-up AI Agent (UPDATED)
Tracks and advances Sales Orders through the complete fulfillment cycle.
Based on SOP: Ciclo de Venta a Compra en ERPNext

UPDATED (2026-03-03) — Added:
  - create_delivery_note(so_name) — auto-creates DN from SO (Step 6)
  - create_sales_invoice(so_name) — auto-creates SI from SO/DN with CFDI (Step 7)
  - create_from_quotation(quotation_name) — creates SO from Quotation (Step 3)
  - Updated STATUS_NEXT_ACTIONS to include manufacturing steps
  - Server Script safe (no import frappe issues)

CFDI Intelligence:
  - Auto-sets mx_cfdi_use to G03 (Gastos en general) for export customers
  - Sets custom_customer_invoice_currency from SO grand_total currency
  - SAT Tax Regime 601 for foreign customers (RFC: XAXX010101000)
"""
import frappe
from typing import Dict, List, Optional
from frappe.utils import nowdate, getdate, add_days, flt


class SalesOrderFollowupAgent:
    """AI Agent for Sales Order follow-up and fulfillment tracking"""

    # Updated status workflow mapping — now includes manufacturing awareness
    STATUS_NEXT_ACTIONS = {
        "Draft": "Submit the Sales Order → then create Work Orders",
        "To Deliver and Bill": (
            "Check inventory → "
            "If stock available: Create Delivery Note → "
            "If no stock: Create Work Order (manufacturing) first"
        ),
        "To Deliver": "Create Delivery Note (billing done, pending delivery)",
        "To Bill": "Create Sales Invoice (delivered, pending billing)",
        "Completed": "Order fully fulfilled — check Payment Entry status",
        "Cancelled": "Order was cancelled — no action needed",
        "Closed": "Order closed — no further action"
    }

    def __init__(self, user: str = None):
        self.user = user or frappe.session.user
        self.site_name = frappe.local.site

    def make_link(self, doctype: str, name: str) -> str:
        """Generate clickable markdown link"""
        slug = doctype.lower().replace(" ", "-")
        return f"[{name}](https://{self.site_name}/app/{slug}/{name})"

    # ========== STATUS & TRACKING ==========

    def get_so_status(self, so_name: str) -> Dict:
        """Get detailed status of a specific Sales Order"""
        try:
            so = frappe.get_doc("Sales Order", so_name)

            # Get linked documents
            delivery_notes = frappe.get_all("Delivery Note Item",
                filters={"against_sales_order": so_name, "docstatus": ["!=", 2]},
                fields=["parent"], distinct=True)

            sales_invoices = frappe.get_all("Sales Invoice Item",
                filters={"sales_order": so_name, "docstatus": ["!=", 2]},
                fields=["parent"], distinct=True)

            material_requests = frappe.get_all("Material Request Item",
                filters={"sales_order": so_name, "docstatus": ["!=", 2]},
                fields=["parent"], distinct=True)

            # NEW: Get linked Work Orders
            work_orders = frappe.get_all("Work Order",
                filters={"sales_order": so_name, "docstatus": ["!=", 2]},
                fields=["name", "status", "production_item", "qty", "produced_qty"],
                order_by="creation")

            # Check inventory for each item
            inventory_status = []
            for item in so.items:
                available = frappe.db.get_value("Bin",
                    {"item_code": item.item_code, "warehouse": item.warehouse},
                    "actual_qty") or 0
                inventory_status.append({
                    "item_code": item.item_code,
                    "ordered_qty": item.qty,
                    "available_qty": available,
                    "sufficient": available >= item.qty
                })

            all_sufficient = all(i["sufficient"] for i in inventory_status)

            return {
                "success": True,
                "so_name": so.name,
                "link": self.make_link("Sales Order", so.name),
                "customer": so.customer,
                "status": so.status,
                "delivery_status": so.delivery_status,
                "billing_status": so.billing_status,
                "grand_total": so.grand_total,
                "currency": so.currency,
                "delivery_date": str(so.delivery_date) if so.delivery_date else None,
                "next_action": self.STATUS_NEXT_ACTIONS.get(so.status, "Review order status"),
                "inventory_sufficient": all_sufficient,
                "inventory_details": inventory_status,
                "linked_documents": {
                    "delivery_notes": [d.parent for d in delivery_notes],
                    "sales_invoices": [i.parent for i in sales_invoices],
                    "material_requests": [m.parent for m in material_requests],
                    "work_orders": [{
                        "name": wo.name,
                        "status": wo.status,
                        "item": wo.production_item,
                        "progress": f"{flt(wo.produced_qty / wo.qty * 100, 1)}%" if wo.qty else "0%"
                    } for wo in work_orders]
                }
            }
        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Sales Order '{so_name}' not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_pending_orders(self, limit: int = 20) -> Dict:
        """List all Sales Orders pending delivery or billing"""
        try:
            orders = frappe.get_all("Sales Order",
                filters={
                    "docstatus": 1,
                    "status": ["in", ["To Deliver and Bill", "To Deliver", "To Bill"]]
                },
                fields=["name", "customer", "status", "grand_total", "delivery_date",
                         "transaction_date", "currency"],
                order_by="delivery_date asc",
                limit=limit)

            result = []
            for so in orders:
                result.append({
                    "name": so.name,
                    "link": self.make_link("Sales Order", so.name),
                    "customer": so.customer,
                    "status": so.status,
                    "grand_total": f"{so.currency} {so.grand_total:,.2f}",
                    "delivery_date": str(so.delivery_date) if so.delivery_date else "Not set",
                    "next_action": self.STATUS_NEXT_ACTIONS.get(so.status, "Review")
                })

            return {
                "success": True,
                "count": len(result),
                "orders": result
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def check_inventory(self, so_name: str) -> Dict:
        """Check item availability for a Sales Order"""
        try:
            so = frappe.get_doc("Sales Order", so_name)

            items = []
            all_available = True

            for item in so.items:
                available = frappe.db.get_value("Bin",
                    {"item_code": item.item_code, "warehouse": item.warehouse},
                    "actual_qty") or 0

                shortage = max(0, item.qty - available)
                sufficient = available >= item.qty

                if not sufficient:
                    all_available = False

                items.append({
                    "item_code": item.item_code,
                    "item_name": item.item_name,
                    "required_qty": item.qty,
                    "available_qty": available,
                    "shortage": shortage,
                    "status": "✅ OK" if sufficient else f"❌ Short by {shortage}"
                })

            recommendation = (
                "Ready for delivery — create Delivery Note"
                if all_available
                else "Create Work Order (manufacturing) or Material Request for missing items"
            )

            return {
                "success": True,
                "so_name": so.name,
                "link": self.make_link("Sales Order", so.name),
                "all_available": all_available,
                "recommendation": recommendation,
                "items": items
            }
        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Sales Order '{so_name}' not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ==========================================================================
    # NEW: STEP 3 — CREATE SO FROM QUOTATION
    # ==========================================================================

    def create_from_quotation(self, quotation_name: str, confirm: bool = False) -> Dict:
        """
        Create Sales Order from a submitted Quotation.
        Handles payment terms, delivery dates, and idempotency.

        Args:
            quotation_name: Quotation name (e.g., SAL-QTN-2024-00001)
            confirm: If False, returns preview
        """
        try:
            from erpnext.selling.doctype.quotation.quotation import make_sales_order

            qtn = frappe.get_doc("Quotation", quotation_name)

            if qtn.docstatus != 1:
                return {
                    "success": False,
                    "error": f"Quotation {quotation_name} must be submitted first (docstatus={qtn.docstatus})"
                }

            # Idempotency: check for existing SO from this Quotation
            existing_so = frappe.db.get_value("Sales Order Item",
                {"prevdoc_docname": quotation_name, "docstatus": ["!=", 2]},
                "parent")
            if existing_so:
                return {
                    "success": True,
                    "action": "existing_found",
                    "message": f"Sales Order already exists: {existing_so}",
                    "sales_order": existing_so,
                    "link": self.make_link("Sales Order", existing_so)
                }

            if not confirm:
                return {
                    "success": True,
                    "requires_confirmation": True,
                    "preview": (
                        f"**Create Sales Order from {quotation_name}?**\n\n"
                        f"| Field | Value |\n|-------|-------|\n"
                        f"| Customer | {qtn.party_name} |\n"
                        f"| Total | {qtn.currency} {qtn.grand_total:,.2f} |\n"
                        f"| Items | {len(qtn.items)} |\n\n"
                        f"⚠️ **Confirm?** Reply: `@ai confirm create SO from {quotation_name}`"
                    )
                }

            # Create SO using ERPNext's built-in method
            so = make_sales_order(quotation_name)
            so.delivery_date = add_days(nowdate(), 7)

            # Fix payment terms — Due Date must be >= Posting Date
            today = nowdate()
            if hasattr(so, 'payment_schedule') and so.payment_schedule:
                for ps in so.payment_schedule:
                    if ps.due_date and str(ps.due_date) < today:
                        ps.due_date = today

            so.flags.ignore_permissions = True
            so.insert()
            frappe.db.commit()

            return {
                "success": True,
                "action": "created",
                "message": f"✅ Sales Order **{so.name}** created from {quotation_name}",
                "sales_order": so.name,
                "link": self.make_link("Sales Order", so.name),
                "customer": so.customer,
                "grand_total": so.grand_total,
                "currency": so.currency
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ==========================================================================
    # NEW: STEP 6 — CREATE DELIVERY NOTE
    # ==========================================================================

    def create_delivery_note(self, so_name: str, confirm: bool = False) -> Dict:
        """
        Create Delivery Note from a submitted Sales Order.

        Pre-checks:
        - SO must be submitted
        - Inventory must be available (checks Bin)
        - No duplicate DN (idempotent)
        - Handles Quality Inspection requirement (warns if needed)

        Args:
            so_name: Sales Order name
            confirm: If False, returns preview
        """
        try:
            from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note

            so = frappe.get_doc("Sales Order", so_name)

            if so.docstatus != 1:
                return {"success": False, "error": f"Sales Order {so_name} must be submitted first"}

            if so.delivery_status == "Fully Delivered":
                return {"success": True, "message": f"Sales Order {so_name} is already fully delivered"}

            # Idempotency: check for existing DN
            existing_dn = frappe.db.get_value("Delivery Note Item",
                {"against_sales_order": so_name, "docstatus": ["!=", 2]},
                "parent")
            if existing_dn:
                return {
                    "success": True,
                    "action": "existing_found",
                    "message": f"Delivery Note already exists: {existing_dn}",
                    "delivery_note": existing_dn,
                    "link": self.make_link("Delivery Note", existing_dn)
                }

            # Check inventory availability
            inv_check = self.check_inventory(so_name)
            if not inv_check.get("all_available"):
                shortage_items = [
                    f"{i['item_code']}: short by {i['shortage']}"
                    for i in inv_check.get("items", []) if i.get("shortage", 0) > 0
                ]
                return {
                    "success": False,
                    "error": (
                        f"Insufficient inventory for {so_name}.\n"
                        f"Shortages:\n" + "\n".join(f"- {s}" for s in shortage_items) + "\n\n"
                        f"Complete manufacturing first: `@ai create work order from {so_name}`"
                    )
                }

            if not confirm:
                items_preview = "\n".join([
                    f"- {i['item_code']}: {i['required_qty']} (available: {i['available_qty']})"
                    for i in inv_check.get("items", [])
                ])
                return {
                    "success": True,
                    "requires_confirmation": True,
                    "preview": (
                        f"**Create Delivery Note from {so_name}?**\n\n"
                        f"Customer: {so.customer}\n"
                        f"Items:\n{items_preview}\n\n"
                        f"⚠️ **Confirm?** Reply: `@ai confirm create DN from {so_name}`"
                    )
                }

            # Create DN using ERPNext's built-in method
            dn = make_delivery_note(so_name)
            dn.flags.ignore_permissions = True
            dn.insert()
            frappe.db.commit()

            # Warn about Quality Inspection if required
            qi_warning = ""
            for item in dn.items:
                qi_required = frappe.db.get_value("Item", item.item_code, "inspection_required_before_delivery")
                if qi_required:
                    qi_warning = (
                        f"\n⚠️ Quality Inspection required for {item.item_code} "
                        f"before DN can be submitted."
                    )
                    break

            return {
                "success": True,
                "action": "created",
                "delivery_note": dn.name,
                "link": self.make_link("Delivery Note", dn.name),
                "sales_order": so_name,
                "status": "Draft",
                "message": (
                    f"✅ Delivery Note **{dn.name}** created from {so_name}.\n"
                    f"Review and submit to confirm delivery.{qi_warning}"
                )
            }
        except Exception as e:
            frappe.log_error(f"SalesOrderFollowupAgent.create_delivery_note error: {str(e)}")
            return {"success": False, "error": str(e)}

    # ==========================================================================
    # NEW: STEP 7 — CREATE SALES INVOICE (with CFDI)
    # ==========================================================================

    def create_sales_invoice(
        self,
        so_name: str,
        cfdi_use: str = "G03",
        confirm: bool = False
    ) -> Dict:
        """
        Create Sales Invoice from Sales Order or Delivery Note.

        CFDI Intelligence:
        - Auto-sets mx_cfdi_use (default G03 = Gastos en general)
        - Sets currency from SO (handles USD invoices for MXN company)
        - Sets SAT payment method based on amount
        - Handles export customers (RFC: XAXX010101000, regime 601)

        Args:
            so_name: Sales Order name
            cfdi_use: SAT CFDI Use code (default: G03)
            confirm: If False, returns preview
        """
        try:
            so = frappe.get_doc("Sales Order", so_name)

            if so.docstatus != 1:
                return {"success": False, "error": f"Sales Order {so_name} must be submitted first"}

            if so.billing_status == "Fully Billed":
                return {"success": True, "message": f"Sales Order {so_name} is already fully billed"}

            # Idempotency: check for existing SI
            existing_si = frappe.db.get_value("Sales Invoice Item",
                {"sales_order": so_name, "docstatus": ["!=", 2]},
                "parent")
            if existing_si:
                return {
                    "success": True,
                    "action": "existing_found",
                    "message": f"Sales Invoice already exists: {existing_si}",
                    "sales_invoice": existing_si,
                    "link": self.make_link("Sales Invoice", existing_si)
                }

            # Check if DN exists and is submitted (preferred path)
            dn_name = frappe.db.get_value("Delivery Note Item",
                {"against_sales_order": so_name, "docstatus": 1},
                "parent")

            if not confirm:
                return {
                    "success": True,
                    "requires_confirmation": True,
                    "preview": (
                        f"**Create Sales Invoice for {so_name}?**\n\n"
                        f"| Field | Value |\n|-------|-------|\n"
                        f"| Customer | {so.customer} |\n"
                        f"| Total | {so.currency} {so.grand_total:,.2f} |\n"
                        f"| CFDI Use | {cfdi_use} |\n"
                        f"| Based on DN | {dn_name or 'Direct from SO'} |\n\n"
                        f"⚠️ **Confirm?** Reply: `@ai confirm create invoice for {so_name}`"
                    )
                }

            # Create SI — prefer from DN if available, else from SO
            if dn_name:
                from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice
                si = make_sales_invoice(dn_name)
            else:
                from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
                si = make_sales_invoice(so_name)

            # ============ CFDI COMPLIANCE ============
            # Set CFDI Use (G03 = Gastos en general, most common for export)
            if hasattr(si, 'mx_cfdi_use'):
                si.mx_cfdi_use = cfdi_use

            # Set currency from SO (handles USD invoices)
            si.currency = so.currency
            if so.currency != frappe.defaults.get_defaults().get("currency", "MXN"):
                si.conversion_rate = so.conversion_rate

            # Set SAT payment method
            if hasattr(si, 'mx_payment_method'):
                # PUE = single payment, PPD = partial payments
                si.mx_payment_method = "PUE"

            # Set customer invoice currency
            if hasattr(si, 'custom_customer_invoice_currency'):
                si.custom_customer_invoice_currency = so.currency

            si.flags.ignore_permissions = True
            si.insert()
            frappe.db.commit()

            return {
                "success": True,
                "action": "created",
                "sales_invoice": si.name,
                "link": self.make_link("Sales Invoice", si.name),
                "sales_order": so_name,
                "delivery_note": dn_name,
                "grand_total": si.grand_total,
                "currency": si.currency,
                "cfdi_use": cfdi_use,
                "status": "Draft",
                "message": (
                    f"✅ Sales Invoice **{si.name}** created for {so_name}\n"
                    f"Total: {si.currency} {si.grand_total:,.2f}\n"
                    f"CFDI: {cfdi_use}\n"
                    f"Review CFDI tab and submit."
                )
            }
        except Exception as e:
            frappe.log_error(f"SalesOrderFollowupAgent.create_sales_invoice error: {str(e)}")
            return {"success": False, "error": str(e)}

    # ========== EXISTING: NEXT STEPS (UPDATED) ==========

    def get_next_steps(self, so_name: str) -> Dict:
        """Recommend next actions based on current SO state — now manufacturing-aware"""
        try:
            so = frappe.get_doc("Sales Order", so_name)

            steps = []

            if so.docstatus == 0:
                steps.append("1. Submit the Sales Order to confirm it")
                return {
                    "success": True,
                    "so_name": so.name,
                    "link": self.make_link("Sales Order", so.name),
                    "status": "Draft",
                    "steps": steps
                }

            if so.status == "Completed":
                # Check if payment exists
                si = frappe.db.get_value("Sales Invoice Item",
                    {"sales_order": so_name, "docstatus": 1}, "parent")
                if si:
                    outstanding = frappe.db.get_value("Sales Invoice", si, "outstanding_amount") or 0
                    if outstanding > 0:
                        steps.append(f"1. Create Payment Entry for {si} (outstanding: {outstanding:,.2f})")
                    else:
                        steps.append("All done — order is fully paid ✅")
                else:
                    steps.append("Order completed — no invoice found (check billing)")
                return {
                    "success": True,
                    "so_name": so.name,
                    "link": self.make_link("Sales Order", so.name),
                    "status": "Completed",
                    "steps": steps
                }

            # Check inventory
            inv_check = self.check_inventory(so_name)

            # Check for existing Work Orders
            work_orders = frappe.get_all("Work Order",
                filters={"sales_order": so_name, "docstatus": ["!=", 2]},
                fields=["name", "status", "production_item"],
                order_by="creation")

            active_wos = [wo for wo in work_orders if wo.status not in ["Completed", "Cancelled"]]

            if so.status in ["To Deliver and Bill", "To Deliver"]:
                if active_wos:
                    steps.append("1. Complete active Work Orders first:")
                    for wo in active_wos:
                        steps.append(f"   - {self.make_link('Work Order', wo.name)}: {wo.status}")
                elif inv_check.get("all_available"):
                    steps.append(f"1. Create Delivery Note — inventory is available")
                    steps.append(f"   Use: `@ai create DN from {so_name}`")
                else:
                    steps.append("1. Create Work Order (manufacturing) — inventory insufficient")
                    steps.append(f"   Use: `@ai create work order from {so_name}`")

            if so.status in ["To Deliver and Bill", "To Bill"]:
                if so.delivery_status == "Fully Delivered":
                    steps.append(f"• Create Sales Invoice: `@ai create invoice for {so_name}`")

            return {
                "success": True,
                "so_name": so.name,
                "link": self.make_link("Sales Order", so.name),
                "status": so.status,
                "delivery_status": so.delivery_status,
                "billing_status": so.billing_status,
                "inventory_available": inv_check.get("all_available", False),
                "active_work_orders": len(active_wos),
                "steps": steps if steps else ["Review order status manually"]
            }
        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Sales Order '{so_name}' not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ========== PURCHASE CYCLE TRACKING (unchanged) ==========

    def track_purchase_cycle(self, so_name: str) -> Dict:
        """Track the complete purchase cycle for a Sales Order"""
        try:
            so = frappe.get_doc("Sales Order", so_name)

            cycle = {
                "sales_order": {"name": so.name, "link": self.make_link("Sales Order", so.name), "status": so.status},
                "material_requests": [],
                "rfqs": [],
                "supplier_quotations": [],
                "purchase_orders": [],
                "purchase_receipts": []
            }

            # Get Material Requests
            mrs = frappe.get_all("Material Request Item",
                filters={"sales_order": so_name},
                fields=["parent"], distinct=True)

            for mr in mrs:
                mr_doc = frappe.get_doc("Material Request", mr.parent)
                cycle["material_requests"].append({
                    "name": mr_doc.name,
                    "link": self.make_link("Material Request", mr_doc.name),
                    "status": mr_doc.status,
                    "docstatus": mr_doc.docstatus
                })

                # Get RFQs from MR
                rfqs = frappe.get_all("Request for Quotation Item",
                    filters={"material_request": mr.parent},
                    fields=["parent"], distinct=True)

                for rfq in rfqs:
                    rfq_doc = frappe.get_doc("Request for Quotation", rfq.parent)
                    cycle["rfqs"].append({
                        "name": rfq_doc.name,
                        "link": self.make_link("Request for Quotation", rfq_doc.name),
                        "status": rfq_doc.status
                    })

            # Get Purchase Orders linked to MRs
            for mr in mrs:
                pos = frappe.get_all("Purchase Order Item",
                    filters={"material_request": mr.parent},
                    fields=["parent"], distinct=True)

                for po in pos:
                    po_doc = frappe.get_doc("Purchase Order", po.parent)
                    if not any(p["name"] == po_doc.name for p in cycle["purchase_orders"]):
                        cycle["purchase_orders"].append({
                            "name": po_doc.name,
                            "link": self.make_link("Purchase Order", po_doc.name),
                            "supplier": po_doc.supplier,
                            "status": po_doc.status
                        })

            return {"success": True, "cycle": cycle}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ========== MAIN HANDLER (UPDATED) ==========

    def process_command(self, message: str) -> str:
        """Process incoming command and return response"""
        message_lower = message.lower().strip()

        # Extract SO name if present
        import re
        so_pattern = r'(SO-\d+-[\w\s]+|SAL-ORD-\d+-\d+)'
        so_match = re.search(so_pattern, message, re.IGNORECASE)
        so_name = so_match.group(1).strip() if so_match else None

        # Extract Quotation name
        qtn_pattern = r'(SAL-QTN-\d+-\d+|QTN-\d+)'
        qtn_match = re.search(qtn_pattern, message, re.IGNORECASE)
        qtn_name = qtn_match.group(1) if qtn_match else None

        confirm = "confirm" in message_lower or message.startswith("!")

        # Route commands
        if "pending" in message_lower or "list" in message_lower:
            result = self.get_pending_orders()
            if result["success"]:
                lines = [f"## Pending Sales Orders ({result['count']} found)\n"]
                for order in result["orders"]:
                    lines.append(f"• {order['link']} | {order['customer']} | {order['status']}")
                    lines.append(f"  Delivery: {order['delivery_date']} | Total: {order['grand_total']}")
                    lines.append(f"  **Next:** {order['next_action']}\n")
                return "\n".join(lines)
            return f"❌ Error: {result['error']}"

        # NEW: Create from Quotation
        if qtn_name and ("create" in message_lower or "convert" in message_lower):
            result = self.create_from_quotation(qtn_name, confirm=confirm)
            return self._format_response(result)

        if so_name:
            # NEW: Create Delivery Note
            if ("delivery" in message_lower or "dn" in message_lower) and "create" in message_lower:
                result = self.create_delivery_note(so_name, confirm=confirm)
                return self._format_response(result)

            # NEW: Create Sales Invoice
            if ("invoice" in message_lower or "si" in message_lower) and "create" in message_lower:
                result = self.create_sales_invoice(so_name, confirm=confirm)
                return self._format_response(result)

            if "inventory" in message_lower or "stock" in message_lower:
                result = self.check_inventory(so_name)
                if result["success"]:
                    lines = [f"## Inventory Check for {result['link']}\n"]
                    for item in result["items"]:
                        lines.append(f"• {item['item_code']}: {item['status']}")
                    lines.append(f"\n**Recommendation:** {result['recommendation']}")
                    return "\n".join(lines)
                return f"❌ Error: {result['error']}"

            if "next" in message_lower or "step" in message_lower:
                result = self.get_next_steps(so_name)
                if result["success"]:
                    lines = [f"## Next Steps for {result['link']} ({result['status']})\n"]
                    for step in result["steps"]:
                        lines.append(step)
                    return "\n".join(lines)
                return f"❌ Error: {result['error']}"

            if "track" in message_lower or "purchase" in message_lower or "cycle" in message_lower:
                result = self.track_purchase_cycle(so_name)
                if result["success"]:
                    cycle = result["cycle"]
                    lines = [f"## Purchase Cycle for {cycle['sales_order']['link']}\n"]
                    lines.append(f"**Status:** {cycle['sales_order']['status']}")
                    lines.append(f"**MRs:** {len(cycle['material_requests'])} | "
                                 f"**RFQs:** {len(cycle['rfqs'])} | "
                                 f"**POs:** {len(cycle['purchase_orders'])}")
                    return "\n".join(lines)
                return f"❌ Error: {result['error']}"

            # Default: show status
            result = self.get_so_status(so_name)
            if result["success"]:
                linked = result["linked_documents"]
                lines = [
                    f"## {result['link']} — {result['status']}\n",
                    f"**Customer:** {result['customer']}",
                    f"**Total:** {result.get('currency', '')} {result['grand_total']:,.2f}",
                    f"**Delivery:** {result['delivery_date'] or 'Not set'}",
                    f"**Inventory:** {'✅ Available' if result['inventory_sufficient'] else '❌ Insufficient'}",
                    f"\n**Linked Documents:**",
                    f"- DNs: {', '.join(linked['delivery_notes']) or 'None'}",
                    f"- SIs: {', '.join(linked['sales_invoices']) or 'None'}",
                    f"- WOs: {len(linked.get('work_orders', []))} work orders",
                    f"\n**Next:** {result['next_action']}"
                ]
                return "\n".join(lines)
            return f"❌ Error: {result['error']}"

        return (
            "**Sales Order Agent Commands:**\n\n"
            "- `@ai pending orders` — List pending SOs\n"
            "- `@ai status SO-00752` — Show SO details\n"
            "- `@ai inventory SO-00752` — Check stock\n"
            "- `@ai next steps SO-00752` — Recommend actions\n"
            "- `@ai create SO from SAL-QTN-2024-00001` — SO from Quotation\n"
            "- `@ai create DN from SO-00752` — Create Delivery Note\n"
            "- `@ai create invoice for SO-00752` — Create Sales Invoice\n"
            "- `@ai track purchase SO-00752` — Track purchase cycle"
        )

    def _format_response(self, result: Dict) -> str:
        """Format result dict into readable response"""
        if result.get("requires_confirmation"):
            return result["preview"]
        if not result.get("success"):
            return f"❌ {result.get('error', 'Unknown error')}"
        if result.get("message"):
            return result["message"]
        return str(result)
