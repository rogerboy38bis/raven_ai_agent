"""
Sales Order Follow-up AI Agent — UPDATED
Tracks and advances Sales Orders through the complete fulfillment cycle.
Based on SOP: Ciclo de Venta a Compra en ERPNext

UPDATED to cover Workflow Steps 3, 6, 7:
  Step 3: SO → Submit (+ auto-create from Quotation)
  Step 6: Delivery Note (auto-create from SO)
  Step 7: Sales Invoice (auto-create from SO/DN with CFDI/currency logic)

Changes from original:
  + create_delivery_note(so_name) — auto-creates DN from SO
  + create_sales_invoice(so_name) — auto-creates SI from SO/DN with CFDI fields
  + create_from_quotation(quotation_name) — creates SO from Quotation
  + submit_sales_order(so_name) — auto-submit SO
  + Updated STATUS_NEXT_ACTIONS to include manufacturing steps
  + Server Script awareness (no import frappe in Server Scripts)

Author: raven_ai_agent
"""
import frappe
from typing import Dict, List, Optional
from frappe.utils import nowdate, getdate, flt
import re


class SalesOrderFollowupAgent:
    """AI Agent for Sales Order follow-up and fulfillment tracking"""
    
    # Status workflow mapping — UPDATED with manufacturing steps
    STATUS_NEXT_ACTIONS = {
        "Draft": "Submit the Sales Order → then create Manufacturing WO",
        "To Deliver and Bill": "Check inventory → If stock available: Create DN; If not: Create Manufacturing WO",
        "To Deliver": "Create Delivery Note (stock must be available in FG to Sell)",
        "To Bill": "Create Sales Invoice (with CFDI G03 for Mexico)",
        "Completed": "Order fully fulfilled — create Payment Entry if outstanding",
        "Cancelled": "Order was cancelled — no action needed",
        "Overdue": "Follow up with customer — order is past delivery date"
    }
    
    def __init__(self, user: str = None):
        self.user = user or frappe.session.user
        self.site_name = frappe.local.site
    
    def make_link(self, doctype: str, name: str) -> str:
        """Generate clickable markdown link"""
        slug = doctype.lower().replace(" ", "-")
        return f"[{name}](https://{self.site_name}/app/{slug}/{name})"
    
    # ========== NEW: DOCUMENT CREATION (Steps 3, 6, 7) ==========

    def submit_sales_order(self, so_name: str) -> Dict:
        """Submit a Sales Order (Step 3).
        
        Args:
            so_name: Sales Order name
        
        Returns:
            Dict with submission status
        """
        try:
            so = frappe.get_doc("Sales Order", so_name)

            if so.docstatus == 1:
                return {
                    "success": True,
                    "message": (
                        f"✅ Sales Order {self.make_link('Sales Order', so_name)} is already submitted.\n"
                        f"  Status: {so.status}\n"
                        f"  ➡️ Next: {self.STATUS_NEXT_ACTIONS.get(so.status, 'Review')}"
                    )
                }
            if so.docstatus == 2:
                return {"success": False, "error": f"Sales Order {so_name} is cancelled."}

            so.submit()
            frappe.db.commit()

            return {
                "success": True,
                "so_name": so.name,
                "link": self.make_link("Sales Order", so.name),
                "message": (
                    f"✅ Sales Order submitted: {self.make_link('Sales Order', so.name)}\n\n"
                    f"  Customer: {so.customer}\n"
                    f"  Grand Total: {so.grand_total} {so.currency}\n"
                    f"  Status: {so.status}\n\n"
                    f"💡 Next steps:\n"
                    f"  1. Create Manufacturing WO: `@manufacturing create wo from so {so.name}`\n"
                    f"  2. Or check inventory: `@sales_order_follow_up inventory {so.name}`"
                )
            }

        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Sales Order '{so_name}' not found."}
        except Exception as e:
            return {"success": False, "error": f"Error submitting SO: {str(e)}"}

    def create_from_quotation(self, quotation_name: str) -> Dict:
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

            if qt.status == "Ordered":
                # Find the existing SO
                existing_so = frappe.db.get_value("Sales Order Item",
                    {"prevdoc_docname": quotation_name}, "parent")
                msg = f"✅ Quotation already ordered."
                if existing_so:
                    msg += f"\n  Sales Order: {self.make_link('Sales Order', existing_so)}"
                return {"success": True, "message": msg}

            from erpnext.selling.doctype.quotation.quotation import make_sales_order
            so = make_sales_order(quotation_name)
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
                    f"  Grand Total: {so.grand_total} {so.currency}\n\n"
                    f"💡 Next: Submit the SO with `@sales_order_follow_up submit {so.name}`"
                )
            }

        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Quotation '{quotation_name}' not found."}
        except Exception as e:
            return {"success": False, "error": f"Error creating SO from Quotation: {str(e)}"}

    def create_delivery_note(self, so_name: str) -> Dict:
        """Create a Delivery Note from a Sales Order (Step 6).
        
        Validates inventory availability before creating the DN.
        
        Args:
            so_name: Sales Order name
        
        Returns:
            Dict with DN details
        """
        try:
            so = frappe.get_doc("Sales Order", so_name)

            if so.docstatus != 1:
                return {"success": False, "error": f"Sales Order '{so_name}' must be submitted first."}

            if so.delivery_status == "Fully Delivered":
                return {"success": True, "message": f"✅ SO {self.make_link('Sales Order', so_name)} is already fully delivered."}

            # Check inventory before creating DN
            shortages = []
            for item in so.items:
                available = frappe.db.get_value("Bin",
                    {"item_code": item.item_code, "warehouse": item.warehouse},
                    "actual_qty") or 0
                if flt(available) < flt(item.qty - (item.delivered_qty or 0)):
                    remaining = flt(item.qty) - flt(item.delivered_qty or 0)
                    shortages.append(
                        f"  ❌ {item.item_code}: need {remaining}, have {available} in {item.warehouse}"
                    )

            if shortages:
                return {
                    "success": False,
                    "error": (
                        f"Cannot create Delivery Note — insufficient stock:\n"
                        + "\n".join(shortages)
                        + f"\n\n💡 Complete manufacturing first:\n"
                        f"  `@manufacturing create wo from so {so_name}`"
                    )
                }

            from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note
            dn = make_delivery_note(so_name)
            dn.insert(ignore_permissions=True)
            dn.submit()
            frappe.db.commit()

            return {
                "success": True,
                "dn_name": dn.name,
                "link": self.make_link("Delivery Note", dn.name),
                "message": (
                    f"✅ Delivery Note created: {self.make_link('Delivery Note', dn.name)}\n\n"
                    f"  Sales Order: {self.make_link('Sales Order', so_name)}\n"
                    f"  Customer: {so.customer}\n"
                    f"  Items: {len(dn.items)}\n\n"
                    f"💡 Next: Create Sales Invoice with `@sales_order_follow_up invoice {so_name}`"
                )
            }

        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Sales Order '{so_name}' not found."}
        except Exception as e:
            return {"success": False, "error": f"Error creating Delivery Note: {str(e)}"}

    def create_sales_invoice(self, so_name: str, from_dn: bool = True) -> Dict:
        """Create a Sales Invoice from a Sales Order/Delivery Note (Step 7).
        
        Includes CFDI compliance: auto-sets mx_cfdi_use to G03,
        sets custom_customer_invoice_currency from SO grand_total currency.
        
        Args:
            so_name: Sales Order name
            from_dn: If True, creates SI from the last DN. If False, from SO directly.
        
        Returns:
            Dict with SI details
        """
        try:
            so = frappe.get_doc("Sales Order", so_name)

            if so.docstatus != 1:
                return {"success": False, "error": f"Sales Order '{so_name}' must be submitted first."}

            if so.billing_status == "Fully Billed":
                return {"success": True, "message": f"✅ SO {self.make_link('Sales Order', so_name)} is already fully billed."}

            si = None

            if from_dn:
                # Try to create from latest Delivery Note
                dns = frappe.get_all("Delivery Note Item",
                    filters={"against_sales_order": so_name, "docstatus": 1},
                    fields=["parent"], distinct=True, order_by="parent desc")

                if dns:
                    dn_name = dns[0].parent
                    # Check if DN already has an invoice
                    existing_si = frappe.get_all("Sales Invoice Item",
                        filters={"delivery_note": dn_name, "docstatus": ["!=", 2]},
                        fields=["parent"], distinct=True)
                    
                    if existing_si:
                        return {
                            "success": True,
                            "message": (
                                f"✅ Delivery Note {self.make_link('Delivery Note', dn_name)} "
                                f"already has invoice: {self.make_link('Sales Invoice', existing_si[0].parent)}"
                            )
                        }

                    from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice
                    si = make_sales_invoice(dn_name)
                else:
                    # Fall back to creating from SO directly
                    from_dn = False

            if not from_dn:
                from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
                si = make_sales_invoice(so_name)

            if not si:
                return {"success": False, "error": "Could not generate Sales Invoice."}

            # CFDI compliance — Mexico invoice fields
            if hasattr(si, "mx_cfdi_use"):
                si.mx_cfdi_use = "G03"  # Gastos en general

            if hasattr(si, "custom_customer_invoice_currency"):
                si.custom_customer_invoice_currency = so.currency

            # Set default mode of payment for Mexico CFDI compliance
            if hasattr(si, "mode_of_payment") and not si.mode_of_payment:
                # Try to get from Customer first
                customer = frappe.get_doc("Customer", so.customer)
                if hasattr(customer, "custom_default_payment_method") and customer.custom_default_payment_method:
                    si.mode_of_payment = customer.custom_default_payment_method
                else:
                    # Get first available Mode of Payment from system
                    mop = frappe.db.get_value("Mode of Payment", {"is_active": 1, "is_cash": 1}, "name")
                    if not mop:
                        mop = frappe.db.get_value("Mode of Payment", {"is_active": 1}, "name")
                    if mop:
                        si.mode_of_payment = mop

            si.insert(ignore_permissions=True)
            si.submit()
            frappe.db.commit()

            cfdi_info = ""
            if hasattr(si, "mx_cfdi_use"):
                cfdi_info = f"\n  CFDI Use: {si.mx_cfdi_use}"

            return {
                "success": True,
                "si_name": si.name,
                "link": self.make_link("Sales Invoice", si.name),
                "message": (
                    f"✅ Sales Invoice created: {self.make_link('Sales Invoice', si.name)}\n\n"
                    f"  Sales Order: {self.make_link('Sales Order', so_name)}\n"
                    f"  Customer: {so.customer}\n"
                    f"  Grand Total: {si.grand_total} {si.currency}"
                    + cfdi_info
                    + f"\n  Outstanding: {si.outstanding_amount}\n\n"
                    f"💡 Next: Create Payment Entry with `@payment create {si.name}`"
                )
            }

        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Sales Order '{so_name}' not found."}
        except Exception as e:
            return {"success": False, "error": f"Error creating Sales Invoice: {str(e)}"}

    # ========== ORIGINAL METHODS (preserved) ==========

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

            # Check Work Orders (NEW)
            work_orders = frappe.get_all("Work Order",
                filters={"sales_order": so_name, "docstatus": ["!=", 2]},
                fields=["name", "status", "production_item", "qty", "produced_qty"])
            
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
                "delivery_date": str(so.delivery_date) if so.delivery_date else None,
                "next_action": self.STATUS_NEXT_ACTIONS.get(so.status, "Review order status"),
                "inventory_sufficient": all_sufficient,
                "inventory_details": inventory_status,
                "linked_documents": {
                    "delivery_notes": [d.parent for d in delivery_notes],
                    "sales_invoices": [i.parent for i in sales_invoices],
                    "material_requests": [m.parent for m in material_requests],
                    "work_orders": [{"name": w.name, "status": w.status, "produced": f"{w.produced_qty}/{w.qty}"} for w in work_orders]
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
                fields=["name", "customer", "status", "grand_total", "delivery_date", "transaction_date"],
                order_by="delivery_date asc",
                limit=limit)
            
            result = []
            for so in orders:
                result.append({
                    "name": so.name,
                    "link": self.make_link("Sales Order", so.name),
                    "customer": so.customer,
                    "status": so.status,
                    "grand_total": so.grand_total,
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
            
            recommendation = "Ready for delivery" if all_available else "Create Material Request or Manufacturing WO for missing items"
            
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

    def get_next_steps(self, so_name: str) -> Dict:
        """Recommend next actions based on current SO state — UPDATED with manufacturing awareness"""
        try:
            so = frappe.get_doc("Sales Order", so_name)
            
            steps = []
            
            if so.docstatus == 0:
                steps.append("1. Submit the Sales Order: `@sales_order_follow_up submit " + so_name + "`")
                return {
                    "success": True,
                    "so_name": so.name,
                    "link": self.make_link("Sales Order", so.name),
                    "status": "Draft",
                    "steps": steps
                }
            
            if so.status == "Completed":
                # Check if payment is pending
                sis = frappe.get_all("Sales Invoice Item",
                    filters={"sales_order": so_name, "docstatus": 1},
                    fields=["parent"], distinct=True)
                has_outstanding = False
                for si_ref in sis:
                    outstanding = frappe.db.get_value("Sales Invoice", si_ref.parent, "outstanding_amount")
                    if flt(outstanding) > 0:
                        has_outstanding = True
                        steps.append(f"1. Payment pending on {self.make_link('Sales Invoice', si_ref.parent)} — Outstanding: {outstanding}")
                        steps.append(f"   `@payment create {si_ref.parent}`")

                if not has_outstanding:
                    steps = ["Order is fully completed and paid — no actions needed"]

                return {
                    "success": True,
                    "so_name": so.name,
                    "link": self.make_link("Sales Order", so.name),
                    "status": "Completed",
                    "steps": steps
                }

            # Check inventory
            inv_check = self.check_inventory(so_name)
            
            # Check existing Work Orders
            existing_wos = frappe.get_all("Work Order",
                filters={"sales_order": so_name, "docstatus": ["!=", 2]},
                fields=["name", "status", "produced_qty", "qty"])

            if so.status in ["To Deliver and Bill", "To Deliver"]:
                if inv_check.get("all_available"):
                    steps.append(f"1. ✅ Inventory available — Create Delivery Note")
                    steps.append(f"   `@sales_order_follow_up delivery {so_name}`")
                else:
                    if existing_wos:
                        for wo in existing_wos:
                            if wo.status not in ["Completed", "Cancelled"]:
                                steps.append(f"1. 🏭 Work Order in progress: {self.make_link('Work Order', wo.name)} ({wo.status})")
                                steps.append(f"   Produced: {wo.produced_qty}/{wo.qty}")
                            elif wo.status == "Completed":
                                steps.append(f"1. ✅ WO Completed: {self.make_link('Work Order', wo.name)}")
                    else:
                        steps.append("1. ❌ Inventory insufficient — Create Manufacturing WO")
                        steps.append(f"   `@manufacturing create wo from so {so_name}`")

            if so.status in ["To Deliver and Bill", "To Bill"]:
                if so.delivery_status == "Fully Delivered":
                    steps.append(f"• Create Sales Invoice: `@sales_order_follow_up invoice {so_name}`")

            if not steps:
                steps = [f"Review order status: {so.status}"]
            
            return {
                "success": True,
                "so_name": so.name,
                "link": self.make_link("Sales Order", so.name),
                "status": so.status,
                "delivery_status": so.delivery_status,
                "billing_status": so.billing_status,
                "inventory_available": inv_check.get("all_available", False),
                "work_orders": existing_wos,
                "steps": steps
            }
        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Sales Order '{so_name}' not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
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
                        "status": rfq_doc.status,
                        "docstatus": rfq_doc.docstatus
                    })
                    
                    # Get Supplier Quotations from RFQ
                    sqs = frappe.get_all("Supplier Quotation Item",
                        filters={"request_for_quotation": rfq.parent},
                        fields=["parent"], distinct=True)
                    
                    for sq in sqs:
                        sq_doc = frappe.get_doc("Supplier Quotation", sq.parent)
                        cycle["supplier_quotations"].append({
                            "name": sq_doc.name,
                            "link": self.make_link("Supplier Quotation", sq_doc.name),
                            "supplier": sq_doc.supplier,
                            "status": sq_doc.status,
                            "docstatus": sq_doc.docstatus
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
                            "status": po_doc.status,
                            "docstatus": po_doc.docstatus
                        })
                        
                        # Get Purchase Receipts
                        prs = frappe.get_all("Purchase Receipt Item",
                            filters={"purchase_order": po.parent},
                            fields=["parent"], distinct=True)
                        
                        for pr in prs:
                            pr_doc = frappe.get_doc("Purchase Receipt", pr.parent)
                            if not any(p["name"] == pr_doc.name for p in cycle["purchase_receipts"]):
                                cycle["purchase_receipts"].append({
                                    "name": pr_doc.name,
                                    "link": self.make_link("Purchase Receipt", pr_doc.name),
                                    "status": pr_doc.status,
                                    "docstatus": pr_doc.docstatus
                                })
            
            return {"success": True, "cycle": cycle}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ========== MAIN HANDLER — UPDATED ==========
    
    def process_command(self, message: str) -> str:
        """Process incoming command and return response — UPDATED with new commands"""
        message_lower = message.lower().strip()
        
        # Extract SO name if present
        so_pattern = r'(SO-[\w-]+|SAL-ORD-[\d-]+)'
        so_match = re.search(so_pattern, message, re.IGNORECASE)
        so_name = so_match.group(1) if so_match else None

        # Extract Quotation name
        qtn_pattern = r'(SAL-QTN-[\d-]+|QTN-[\d-]+)'
        qtn_match = re.search(qtn_pattern, message, re.IGNORECASE)
        qtn_name = qtn_match.group(1) if qtn_match else None
        
        # ---- HELP ----
        if "help" in message_lower or "capabilities" in message_lower:
            return self._help_text()

        # ---- CREATE SO FROM QUOTATION (NEW) ----
        if ("create" in message_lower and "from" in message_lower
                and ("quotation" in message_lower or "qtn" in message_lower)):
            if not qtn_name:
                return "❌ Please specify a Quotation. Example: `@sales_order_follow_up create from quotation SAL-QTN-2024-00752`"
            result = self.create_from_quotation(qtn_name)
            return result.get("message", result.get("error", "Unknown error"))

        # ---- SUBMIT SO (NEW) ----
        if "submit" in message_lower and so_name:
            result = self.submit_sales_order(so_name)
            return result.get("message", result.get("error", "Unknown error"))

        # ---- CREATE DELIVERY NOTE (NEW — Step 6) ----
        if ("delivery" in message_lower or "dn" in message_lower or "entregar" in message_lower) and so_name:
            result = self.create_delivery_note(so_name)
            return result.get("message", result.get("error", "Unknown error"))

        # ---- CREATE SALES INVOICE (NEW — Step 7) ----
        if ("invoice" in message_lower or "factura" in message_lower
                or "bill" in message_lower or "si" in message_lower) and so_name:
            from_dn = "from dn" in message_lower or "from delivery" in message_lower or "dn" not in message_lower
            result = self.create_sales_invoice(so_name, from_dn=from_dn)
            return result.get("message", result.get("error", "Unknown error"))

        # ---- PENDING ORDERS ----
        if "pending" in message_lower or "list" in message_lower or "pendientes" in message_lower:
            result = self.get_pending_orders()
            if result["success"]:
                lines = [f"## Pending Sales Orders ({result['count']} found)\n"]
                for order in result["orders"]:
                    lines.append(f"• {order['link']} | {order['customer']} | {order['status']}")
                    lines.append(f"  Delivery: {order['delivery_date']} | Total: {order['grand_total']}")
                    lines.append(f"  ➡️ {order['next_action']}")
                return "\n".join(lines) if result["count"] > 0 else "✅ No pending sales orders."
            return f"❌ Error: {result['error']}"
        
        # ---- STATUS ----
        if ("status" in message_lower or "estado" in message_lower) and so_name:
            result = self.get_so_status(so_name)
            if result["success"]:
                msg = (
                    f"📋 **{result['link']}**\n\n"
                    f"  Customer: {result['customer']}\n"
                    f"  Status: **{result['status']}**\n"
                    f"  Delivery: {result['delivery_status']} | Billing: {result['billing_status']}\n"
                    f"  Total: {result['grand_total']}\n"
                    f"  Delivery Date: {result['delivery_date']}\n"
                    f"  Inventory: {'✅ Sufficient' if result['inventory_sufficient'] else '❌ Insufficient'}\n\n"
                    f"  ➡️ **Next:** {result['next_action']}\n"
                )
                # Show linked Work Orders (NEW)
                wos = result["linked_documents"].get("work_orders", [])
                if wos:
                    msg += "\n🏭 **Work Orders:**\n"
                    for wo in wos:
                        msg += f"  • {self.make_link('Work Order', wo['name'])} — {wo['status']} ({wo['produced']})\n"

                linked = result["linked_documents"]
                if linked["delivery_notes"]:
                    msg += "\n📦 Delivery Notes: " + ", ".join(self.make_link("Delivery Note", d) for d in linked["delivery_notes"])
                if linked["sales_invoices"]:
                    msg += "\n🧾 Sales Invoices: " + ", ".join(self.make_link("Sales Invoice", i) for i in linked["sales_invoices"])
                return msg
            return f"❌ {result['error']}"

        # ---- INVENTORY CHECK ----
        if ("inventory" in message_lower or "stock" in message_lower
                or "inventario" in message_lower) and so_name:
            result = self.check_inventory(so_name)
            if result["success"]:
                msg = f"📦 **Inventory Check for {result['link']}**\n\n"
                for item in result["items"]:
                    msg += f"  {item['status']} {item['item_code']} — Need: {item['required_qty']}, Have: {item['available_qty']}\n"
                msg += f"\n💡 {result['recommendation']}"
                return msg
            return f"❌ {result['error']}"
        
        # ---- NEXT STEPS ----
        if ("next" in message_lower or "que sigue" in message_lower
                or "recommend" in message_lower) and so_name:
            result = self.get_next_steps(so_name)
            if result["success"]:
                msg = f"📋 **Next Steps for {result['link']}** (Status: {result['status']})\n\n"
                for step in result["steps"]:
                    msg += f"{step}\n"
                return msg
            return f"❌ {result['error']}"
        
        # ---- TRACK PURCHASE CYCLE ----
        if ("track" in message_lower or "cycle" in message_lower
                or "ciclo" in message_lower) and so_name:
            result = self.track_purchase_cycle(so_name)
            if result["success"]:
                cycle = result["cycle"]
                msg = f"🔄 **Purchase Cycle for {cycle['sales_order']['link']}** ({cycle['sales_order']['status']})\n\n"
                
                sections = [
                    ("📋 Material Requests", cycle["material_requests"]),
                    ("📩 RFQs", cycle["rfqs"]),
                    ("💰 Supplier Quotations", cycle["supplier_quotations"]),
                    ("📦 Purchase Orders", cycle["purchase_orders"]),
                    ("✅ Purchase Receipts", cycle["purchase_receipts"])
                ]
                for title, items in sections:
                    if items:
                        msg += f"\n{title}:\n"
                        for item in items:
                            msg += f"  • {item['link']} — {item.get('status', 'N/A')}\n"
                
                return msg
            return f"❌ {result['error']}"

        # ---- FALLBACK ----
        if so_name:
            result = self.get_so_status(so_name)
            if result["success"]:
                return (
                    f"Sales Order {result['link']} — {result['status']}\n"
                    f"➡️ {result['next_action']}\n\n"
                    f"Use `@sales_order_follow_up help` for all commands."
                )

        return self._help_text()

    def _help_text(self) -> str:
        return (
            "📋 **Sales Order Follow-up Agent — Commands**\n\n"
            "**Document Creation (NEW)**\n"
            "`@sales_order_follow_up create from quotation [QTN-NAME]` — Create SO from Quotation\n"
            "`@sales_order_follow_up submit [SO-NAME]` — Submit Sales Order\n"
            "`@sales_order_follow_up delivery [SO-NAME]` — Create Delivery Note\n"
            "`@sales_order_follow_up invoice [SO-NAME]` — Create Sales Invoice (CFDI G03)\n\n"
            "**Status & Tracking**\n"
            "`@sales_order_follow_up pending` — List pending orders\n"
            "`@sales_order_follow_up status [SO-NAME]` — Detailed SO status\n"
            "`@sales_order_follow_up inventory [SO-NAME]` — Check stock availability\n"
            "`@sales_order_follow_up next [SO-NAME]` — Recommended next actions\n"
            "`@sales_order_follow_up track [SO-NAME]` — Full purchase cycle tracking\n\n"
            "**Example (Full Cycle)**\n"
            "```\n"
            "@sales_order_follow_up create from quotation SAL-QTN-2024-00752\n"
            "@sales_order_follow_up submit SO-00752-LEGOSAN AB\n"
            "@sales_order_follow_up delivery SO-00752-LEGOSAN AB\n"
            "@sales_order_follow_up invoice SO-00752-LEGOSAN AB\n"
            "```"
        )
