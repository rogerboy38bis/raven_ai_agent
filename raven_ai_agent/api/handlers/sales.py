"""
Sales-to-Purchase Cycle SOP
"""
import frappe
import json
import re
import requests
from typing import Optional, Dict, List


class SalesMixin:
    """Mixin for _handle_sales_commands"""

    def _handle_sales_commands(self, query: str, query_lower: str, is_confirm: bool = False) -> Optional[Dict]:
        """Dispatched from execute_workflow_command"""
        # ==================== SALES-TO-PURCHASE CYCLE SOP ====================
        
        # Show Opportunities
        if "show opportunit" in query_lower or "list opportunit" in query_lower or "oportunidades" in query_lower:
            try:
                opportunities = frappe.get_list("Opportunity",
                    filters={"status": ["not in", ["Lost", "Closed"]]},
                    fields=["name", "party_name", "opportunity_amount", "status", "expected_closing", "sales_stage"],
                    order_by="modified desc",
                    limit=15
                )
                if opportunities:
                    site_name = frappe.local.site
                    opp_list = []
                    for opp in opportunities:
                        amt = f"${opp.opportunity_amount:,.2f}" if opp.opportunity_amount else "—"
                        opp_link = f"https://{site_name}/app/opportunity/{opp.name}"
                        opp_list.append(f"• **[{opp.name}]({opp_link})**\n   {opp.party_name} · {amt} · {opp.status}")
                    return {
                        "success": True,
                        "message": f"🎯 **SALES OPPORTUNITIES**\n\n" + "\n\n".join(opp_list)
                    }
                return {"success": True, "message": "No active opportunities found."}
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Create Opportunity
        if "create opportunit" in query_lower or "crear oportunidad" in query_lower:
            customer_match = re.search(r'(?:for|para)\s+["\']?(.+?)["\']?\s*$', query, re.IGNORECASE)
            if customer_match:
                customer_name = customer_match.group(1).strip()
                try:
                    # Find customer
                    customer = frappe.db.get_value("Customer", {"customer_name": ["like", f"%{customer_name}%"]}, "name")
                    if not customer:
                        return {"success": False, "error": f"Customer '{customer_name}' not found. Create customer first."}
                    
                    if not is_confirm:
                        return {
                            "requires_confirmation": True,
                            "preview": f"🎯 CREATE OPPORTUNITY?\n\n  Customer: {customer}\n\nSay 'confirm' to proceed."
                        }
                    
                    opp = frappe.get_doc({
                        "doctype": "Opportunity",
                        "opportunity_from": "Customer",
                        "party_name": customer,
                        "status": "Open",
                        "sales_stage": "Prospecting"
                    })
                    opp.insert()
                    site_name = frappe.local.site
                    return {
                        "success": True,
                        "message": f"✅ Opportunity created: [{opp.name}](https://{site_name}/app/opportunity/{opp.name})"
                    }
                except Exception as e:
                    return {"success": False, "error": str(e)}
        
        # Check Inventory for Sales Order
        so_match = re.search(r'(SAL-ORD-\d+-\d+|SO-[\w\-]+(?:\s+(?!from\b|to\b|pipeline\b|status\b|check\b|audit\b|validate\b|diagnose\b|bom\b|qty\b|quantity\b|item\b|warehouse\b|wh\b)[\w\.]+)*)', query, re.IGNORECASE)
        if so_match and ("check inventory" in query_lower or "verificar inventario" in query_lower or "disponibilidad" in query_lower):
            try:
                so_name = so_match.group(1)
                so = frappe.get_doc("Sales Order", so_name)
                items_status = []
                all_available = True
                for item in so.items:
                    available = frappe.db.get_value("Bin", 
                        {"item_code": item.item_code, "warehouse": item.warehouse},
                        "actual_qty") or 0
                    status = "✅" if available >= item.qty else "❌"
                    if available < item.qty:
                        all_available = False
                    items_status.append(f"  {status} {item.item_code}: Need {item.qty}, Available {available}")
                
                summary = "✅ All items available!" if all_available else "⚠️ Some items need to be purchased"
                return {
                    "success": True,
                    "message": f"📦 INVENTORY CHECK FOR {so_name}:\n{summary}\n\n" + "\n".join(items_status)
                }
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Create Material Request from Sales Order
        if so_match and ("create material request" in query_lower or "crear solicitud de material" in query_lower):
            try:
                so_name = so_match.group(1)
                so = frappe.get_doc("Sales Order", so_name)
                
                # Check which items need purchasing
                items_to_request = []
                for item in so.items:
                    available = frappe.db.get_value("Bin", 
                        {"item_code": item.item_code, "warehouse": item.warehouse},
                        "actual_qty") or 0
                    if available < item.qty:
                        items_to_request.append({
                            "item_code": item.item_code,
                            "qty": item.qty - available,
                            "schedule_date": so.delivery_date or frappe.utils.nowdate(),
                            "warehouse": item.warehouse
                        })
                
                if not items_to_request:
                    return {"success": True, "message": f"✅ All items for {so_name} are in stock. No Material Request needed."}
                
                if not is_confirm:
                    items_preview = [f"  - {i['item_code']}: {i['qty']}" for i in items_to_request[:5]]
                    return {
                        "requires_confirmation": True,
                        "preview": f"📋 CREATE MATERIAL REQUEST FOR {so_name}?\n\nItems to purchase:\n" + "\n".join(items_preview) + "\n\nSay 'confirm' to proceed."
                    }
                
                mr = frappe.get_doc({
                    "doctype": "Material Request",
                    "material_request_type": "Purchase",
                    "schedule_date": so.delivery_date or frappe.utils.nowdate(),
                    "items": items_to_request
                })
                mr.insert()
                site_name = frappe.local.site
                return {
                    "success": True,
                    "message": f"✅ Material Request created: [{mr.name}](https://{site_name}/app/material-request/{mr.name})"
                }
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Show Material Requests
        if "show material request" in query_lower or "list material request" in query_lower or "solicitudes de material" in query_lower:
            try:
                mrs = frappe.get_list("Material Request",
                    filters={"docstatus": ["<", 2], "status": ["not in", ["Stopped", "Cancelled"]]},
                    fields=["name", "material_request_type", "status", "schedule_date", "per_ordered"],
                    order_by="modified desc",
                    limit=15
                )
                if mrs:
                    site_name = frappe.local.site
                    msg = "📋 **MATERIAL REQUESTS**\n\n"
                    msg += "| MR | Type | Status | Schedule | Ordered |\n"
                    msg += "|----|------|--------|----------|---------|\n"
                    for mr in mrs:
                        ordered = f"{mr.per_ordered or 0:.0f}%"
                        mr_link = f"[{mr.name}](https://{site_name}/app/material-request/{mr.name})"
                        msg += f"| {mr_link} | {mr.material_request_type} | {mr.status} | {mr.schedule_date} | {ordered} |\n"
                    return {"success": True, "message": msg}
                return {"success": True, "message": "No pending material requests found."}
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Create RFQ from Material Request
        mr_match = re.search(r'(MAT-MR-\d+-\d+|MR-[^\s]+)', query, re.IGNORECASE)
        if mr_match and ("create rfq" in query_lower or "crear solicitud de cotizacion" in query_lower):
            try:
                mr_name = mr_match.group(1)
                mr = frappe.get_doc("Material Request", mr_name)
                
                if not is_confirm:
                    items_preview = [f"  - {i.item_code}: {i.qty}" for i in mr.items[:5]]
                    return {
                        "requires_confirmation": True,
                        "preview": f"📨 CREATE RFQ FROM {mr_name}?\n\nItems:\n" + "\n".join(items_preview) + "\n\n⚠️ You'll need to add suppliers after creation.\nSay 'confirm' to proceed."
                    }
                
                rfq = frappe.get_doc({
                    "doctype": "Request for Quotation",
                    "transaction_date": frappe.utils.nowdate(),
                    "items": [{
                        "item_code": item.item_code,
                        "qty": item.qty,
                        "schedule_date": item.schedule_date,
                        "warehouse": item.warehouse,
                        "material_request": mr_name,
                        "material_request_item": item.name
                    } for item in mr.items]
                })
                rfq.insert()
                site_name = frappe.local.site
                return {
                    "success": True,
                    "message": f"✅ RFQ created: [{rfq.name}](https://{site_name}/app/request-for-quotation/{rfq.name})\n\n⚠️ Add suppliers and send for quotation."
                }
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Show RFQs
        if "show rfq" in query_lower or "list rfq" in query_lower or "solicitudes de cotizacion" in query_lower:
            try:
                rfqs = frappe.get_list("Request for Quotation",
                    filters={"docstatus": ["<", 2]},
                    fields=["name", "status", "transaction_date", "message_for_supplier"],
                    order_by="modified desc",
                    limit=15
                )
                if rfqs:
                    site_name = frappe.local.site
                    msg = "📨 **REQUEST FOR QUOTATIONS**\n\n"
                    msg += "| RFQ | Status | Date |\n"
                    msg += "|-----|--------|------|\n"
                    for r in rfqs:
                        rfq_link = f"[{r.name}](https://{site_name}/app/request-for-quotation/{r.name})"
                        msg += f"| {rfq_link} | {r.status} | {r.transaction_date} |\n"
                    return {"success": True, "message": msg}
                return {"success": True, "message": "No RFQs found."}
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Show Supplier Quotations
        if "show supplier quotation" in query_lower or "supplier quote" in query_lower or "cotizacion proveedor" in query_lower:
            try:
                sqs = frappe.get_list("Supplier Quotation",
                    filters={"docstatus": ["<", 2]},
                    fields=["name", "supplier", "grand_total", "status", "transaction_date"],
                    order_by="modified desc",
                    limit=15
                )
                if sqs:
                    site_name = frappe.local.site
                    msg = "📄 **SUPPLIER QUOTATIONS**\n\n"
                    msg += "| Quotation | Supplier | Amount | Status | Date |\n"
                    msg += "|-----------|----------|--------|--------|------|\n"
                    for sq in sqs:
                        amt = f"${sq.grand_total:,.2f}" if sq.grand_total else "—"
                        sq_link = f"[{sq.name}](https://{site_name}/app/supplier-quotation/{sq.name})"
                        msg += f"| {sq_link} | {sq.supplier} | {amt} | {sq.status} | {sq.transaction_date} |\n"
                    return {"success": True, "message": msg}
                return {"success": True, "message": "No supplier quotations found."}
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Create Purchase Order from Supplier Quotation
        sq_match = re.search(r'(PUR-SQTN-\d+-\d+|SQ-[^\s]+)', query, re.IGNORECASE)
        if sq_match and ("create po" in query_lower or "create purchase order" in query_lower or "crear orden de compra" in query_lower):
            try:
                sq_name = sq_match.group(1)
                sq = frappe.get_doc("Supplier Quotation", sq_name)
                
                if not is_confirm:
                    items_preview = [f"  - {i.item_code}: {i.qty} @ ${i.rate:,.2f}" for i in sq.items[:5]]
                    return {
                        "requires_confirmation": True,
                        "preview": f"🛒 CREATE PURCHASE ORDER FROM {sq_name}?\n\n  Supplier: {sq.supplier}\n  Total: ${sq.grand_total:,.2f}\n\nItems:\n" + "\n".join(items_preview) + "\n\nSay 'confirm' to proceed."
                    }
                
                po = frappe.get_doc({
                    "doctype": "Purchase Order",
                    "supplier": sq.supplier,
                    "items": [{
                        "item_code": item.item_code,
                        "qty": item.qty,
                        "rate": item.rate,
                        "schedule_date": item.schedule_date or frappe.utils.add_days(frappe.utils.nowdate(), 7),
                        "warehouse": item.warehouse,
                        "supplier_quotation": sq_name,
                        "supplier_quotation_item": item.name
                    } for item in sq.items]
                })
                po.insert()
                site_name = frappe.local.site
                return {
                    "success": True,
                    "message": f"✅ Purchase Order created: [{po.name}](https://{site_name}/app/purchase-order/{po.name})"
                }
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Show Purchase Orders
        if "show purchase order" in query_lower or "list purchase order" in query_lower or "ordenes de compra" in query_lower:
            try:
                pos = frappe.get_list("Purchase Order",
                    filters={"docstatus": ["<", 2]},
                    fields=["name", "supplier", "grand_total", "status", "per_received", "transaction_date"],
                    order_by="modified desc",
                    limit=15
                )
                if pos:
                    site_name = frappe.local.site
                    msg = "🛒 **PURCHASE ORDERS**\n\n"
                    msg += "| PO | Supplier | Amount | Status | Received | Date |\n"
                    msg += "|----|----------|--------|--------|----------|------|\n"
                    for po in pos:
                        amt = f"${po.grand_total:,.2f}" if po.grand_total else "—"
                        received = f"{po.per_received or 0:.0f}%"
                        po_link = f"[{po.name}](https://{site_name}/app/purchase-order/{po.name})"
                        msg += f"| {po_link} | {po.supplier} | {amt} | {po.status} | {received} | {po.transaction_date} |\n"
                    return {"success": True, "message": msg}
                return {"success": True, "message": "No purchase orders found."}
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Receive Goods (Purchase Receipt from PO)
        po_match = re.search(r'(PUR-ORD-\d+-\d+|PO-[^\s]+)', query, re.IGNORECASE)
        if po_match and ("receive goods" in query_lower or "recibir mercancia" in query_lower or "purchase receipt" in query_lower):
            try:
                po_name = po_match.group(1)
                po = frappe.get_doc("Purchase Order", po_name)
                
                # Check pending items
                pending_items = []
                for item in po.items:
                    pending = item.qty - (item.received_qty or 0)
                    if pending > 0:
                        pending_items.append({
                            "item_code": item.item_code,
                            "qty": pending,
                            "rate": item.rate,
                            "warehouse": item.warehouse,
                            "purchase_order": po_name,
                            "purchase_order_item": item.name
                        })
                
                if not pending_items:
                    return {"success": True, "message": f"✅ All items from {po_name} already received."}
                
                if not is_confirm:
                    items_preview = [f"  - {i['item_code']}: {i['qty']}" for i in pending_items[:5]]
                    return {
                        "requires_confirmation": True,
                        "preview": f"📥 RECEIVE GOODS FOR {po_name}?\n\n  Supplier: {po.supplier}\n\nPending Items:\n" + "\n".join(items_preview) + "\n\nSay 'confirm' to create Purchase Receipt."
                    }
                
                pr = frappe.get_doc({
                    "doctype": "Purchase Receipt",
                    "supplier": po.supplier,
                    "items": pending_items
                })
                pr.insert()
                site_name = frappe.local.site
                return {
                    "success": True,
                    "message": f"✅ Purchase Receipt created: [{pr.name}](https://{site_name}/app/purchase-receipt/{pr.name})\n\nVerify quantities and submit to update stock."
                }
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Create Purchase Invoice from PO
        if po_match and ("create purchase invoice" in query_lower or "bill" in query_lower or "factura de compra" in query_lower):
            try:
                po_name = po_match.group(1)
                po = frappe.get_doc("Purchase Order", po_name)
                
                if not is_confirm:
                    return {
                        "requires_confirmation": True,
                        "preview": f"🧾 CREATE PURCHASE INVOICE FOR {po_name}?\n\n  Supplier: {po.supplier}\n  Total: ${po.grand_total:,.2f}\n\nSay 'confirm' to proceed."
                    }
                
                pi = frappe.get_doc({
                    "doctype": "Purchase Invoice",
                    "supplier": po.supplier,
                    "items": [{
                        "item_code": item.item_code,
                        "qty": item.qty,
                        "rate": item.rate,
                        "warehouse": item.warehouse,
                        "purchase_order": po_name
                    } for item in po.items]
                })
                pi.insert()
                site_name = frappe.local.site
                return {
                    "success": True,
                    "message": f"✅ Purchase Invoice created: [{pi.name}](https://{site_name}/app/purchase-invoice/{pi.name})"
                }
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Create Delivery Note from Sales Order
        if so_match and ("create delivery" in query_lower or "ship" in query_lower or "deliver" in query_lower or "nota de entrega" in query_lower or "!delivery" in query_lower or "delivery note" in query_lower):
            try:
                so_name = so_match.group(1)
                so = frappe.get_doc("Sales Order", so_name)
                
                # Check pending items
                pending_items = []
                for item in so.items:
                    pending = item.qty - (item.delivered_qty or 0)
                    if pending > 0:
                        pending_items.append({
                            "item_code": item.item_code,
                            "qty": pending,
                            "rate": item.rate,
                            "warehouse": item.warehouse,
                            "against_sales_order": so_name,
                            "so_detail": item.name
                        })
                
                if not pending_items:
                    return {"success": True, "message": f"✅ All items from {so_name} already delivered."}
                
                if not is_confirm:
                    items_preview = [f"  - {i['item_code']}: {i['qty']}" for i in pending_items[:5]]
                    return {
                        "requires_confirmation": True,
                        "preview": f"🚚 CREATE DELIVERY NOTE FOR {so_name}?\n\n  Customer: {so.customer}\n\nItems to ship:\n" + "\n".join(items_preview) + "\n\nSay 'confirm' to proceed."
                    }
                
                dn = frappe.get_doc({
                    "doctype": "Delivery Note",
                    "customer": so.customer,
                    "items": pending_items
                })
                dn.insert()
                site_name = frappe.local.site
                return {
                    "success": True,
                    "message": f"✅ Delivery Note created: [{dn.name}](https://{site_name}/app/delivery-note/{dn.name})"
                }
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Create Sales Invoice from SO or DN
        dn_match = re.search(r'(MAT-DN-\d+-\d+|DN-[^\s]+)', query, re.IGNORECASE)
        if (so_match or dn_match) and ("create sales invoice" in query_lower or "factura de venta" in query_lower or "invoice customer" in query_lower or "!invoice" in query_lower or "sales invoice" in query_lower or "create invoice" in query_lower):
            try:
                if dn_match:
                    dn_name = dn_match.group(1)
                    dn = frappe.get_doc("Delivery Note", dn_name)
                    
                    if not is_confirm:
                        return {
                            "requires_confirmation": True,
                            "preview": f"🧾 CREATE SALES INVOICE FROM {dn_name}?\n\n  Customer: {dn.customer}\n  Total: ${dn.grand_total:,.2f}\n\nSay 'confirm' to proceed."
                        }
                    
                    si = frappe.get_doc({
                        "doctype": "Sales Invoice",
                        "customer": dn.customer,
                        "items": [{
                            "item_code": item.item_code,
                            "qty": item.qty,
                            "rate": item.rate,
                            "warehouse": item.warehouse,
                            "delivery_note": dn_name,
                            "dn_detail": item.name
                        } for item in dn.items]
                    })
                    si.insert()
                    site_name = frappe.local.site
                    return {
                        "success": True,
                        "message": f"✅ Sales Invoice created: [{si.name}](https://{site_name}/app/sales-invoice/{si.name})"
                    }
                elif so_match:
                    so_name = so_match.group(1)
                    so = frappe.get_doc("Sales Order", so_name)
                    
                    if not is_confirm:
                        return {
                            "requires_confirmation": True,
                            "preview": f"🧾 CREATE SALES INVOICE FROM {so_name}?\n\n  Customer: {so.customer}\n  Total: ${so.grand_total:,.2f}\n\nSay 'confirm' to proceed."
                        }
                    
                    si = frappe.get_doc({
                        "doctype": "Sales Invoice",
                        "customer": so.customer,
                        "items": [{
                            "item_code": item.item_code,
                            "qty": item.qty,
                            "rate": item.rate,
                            "warehouse": item.warehouse,
                            "sales_order": so_name,
                            "so_detail": item.name
                        } for item in so.items]
                    })
                    si.insert()
                    site_name = frappe.local.site
                    return {
                        "success": True,
                        "message": f"✅ Sales Invoice created: [{si.name}](https://{site_name}/app/sales-invoice/{si.name})"
                    }
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # ==================== END SALES-TO-PURCHASE CYCLE SOP ====================

        return None
