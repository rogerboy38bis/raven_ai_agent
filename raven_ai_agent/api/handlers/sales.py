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

    @staticmethod
    def _discover_mx_cfdi_fields(source_doc):
        """Intelligently discover Mexico CFDI fields for Sales Invoice.
        
        Reads payment terms from the source document (SO or DN) to determine:
        - mx_payment_option: PUE (advance/immediate) vs PPD (credit/deferred)
        - mx_cfdi_use: From customer's last invoice, or G01 (goods) default
        - mode_of_payment: From customer's last invoice, or Wire Transfer default
        
        Returns dict of field:value to set on the SI before insert.
        """
        cfdi = {}
        
        # --- 1. Payment Option: PUE vs PPD based on payment terms ---
        payment_terms = getattr(source_doc, 'payment_terms_template', '') or ''
        pt_lower = payment_terms.lower()
        
        # PUE = advance, immediate, anticipado, contado, cash
        # PPD = credit, days, parcialidades, diferido
        pue_keywords = ['advance', 'anticipad', 'contado', 'cash', 'immediate', 'inmediato', 'pue', 'prepaid', 'adelant', 'previo', 'antes']
        ppd_keywords = ['days', 'dias', 'credit', 'credito', 'net ', 'parcialidad', 'diferido', 'ppd',
                        'after', 'reception', 'recepcion', 'delivery', 'entrega']
        
        if any(kw in pt_lower for kw in pue_keywords):
            cfdi['mx_payment_option'] = 'PUE'
        elif any(kw in pt_lower for kw in ppd_keywords):
            cfdi['mx_payment_option'] = 'PPD'
        else:
            # BUG16 fix: Default to PPD (safer — PUE is the special case for advance only)
            # PPD allows deferred payment complement; PUE requires full payment proof at invoice time
            cfdi['mx_payment_option'] = 'PPD'
        
        # --- 2. Discover CFDI Use + Mode of Payment from customer's last invoice ---
        customer = getattr(source_doc, 'customer', None)
        if customer:
            try:
                last_si = frappe.get_all(
                    'Sales Invoice',
                    filters={'customer': customer, 'docstatus': 1},
                    fields=['mx_cfdi_use', 'mode_of_payment'],
                    order_by='posting_date desc',
                    limit_page_length=1
                )
                if last_si:
                    if last_si[0].get('mx_cfdi_use'):
                        cfdi['mx_cfdi_use'] = last_si[0]['mx_cfdi_use']
                    if last_si[0].get('mode_of_payment'):
                        cfdi['mode_of_payment'] = last_si[0]['mode_of_payment']
            except Exception:
                pass  # Discovery is best-effort, defaults below
        
        # --- 3. Smart defaults for anything not discovered ---
        # G01 = Adquisición de mercancías (goods purchase) — most common for product sales
        # G03 = Gastos en general — fallback for services
        if 'mx_cfdi_use' not in cfdi:
            cfdi['mx_cfdi_use'] = 'G01'
        
        if 'mode_of_payment' not in cfdi:
            cfdi['mode_of_payment'] = 'Wire Transfer'
        
        return cfdi

    @staticmethod
    def _discover_conversion_rate(si_doc):
        """Set the correct Banxico FIX T-1 exchange rate on a Sales Invoice.
        
        SAT/CFDI Rule (Anexo 20 Guía de Llenado):
          - TipoCambio on CFDI de ingresos must be the FIX rate
          - FIX is determined by Banxico at noon, published in DOF next business day
          - For invoice date T: use FIX from T-1 (previous business day)
        
        If Banxico API is not available (no token configured), falls back to
        ERPNext's Currency Exchange table or the rate already on the doc.
        
        Args:
            si_doc: The Sales Invoice doc (before insert)
        
        Returns:
            dict with rate info, or None if no change needed
        """
        currency = getattr(si_doc, 'currency', None)
        company = getattr(si_doc, 'company', None)
        posting_date = str(getattr(si_doc, 'posting_date', None) or '')
        
        if not currency or not company or not posting_date:
            return None
        
        # Only applies to foreign currency invoices
        company_currency = frappe.db.get_value('Company', company, 'default_currency') or 'MXN'
        if currency == company_currency:
            return None  # MXN invoice, no conversion needed
        
        # Try Banxico FIX T-1
        try:
            from raven_ai_agent.api.banxico_fx import get_fix_for_invoice
            rate, rate_date = get_fix_for_invoice(posting_date)
            if rate:
                old_rate = getattr(si_doc, 'conversion_rate', None)
                si_doc.conversion_rate = rate
                return {
                    'source': 'banxico_fix',
                    'rate': rate,
                    'rate_date': rate_date,
                    'old_rate': old_rate,
                    'posting_date': posting_date
                }
        except Exception:
            pass  # Banxico API not available, fall through
        
        # Fallback: check ERPNext Currency Exchange table for T-1
        try:
            from datetime import datetime, timedelta
            dt = datetime.strptime(posting_date, "%Y-%m-%d")
            for days_back in range(1, 10):
                check_date = (dt - timedelta(days=days_back)).strftime("%Y-%m-%d")
                ce_rate = frappe.db.get_value(
                    'Currency Exchange',
                    {'date': check_date, 'from_currency': currency, 'to_currency': company_currency},
                    'exchange_rate'
                )
                if ce_rate:
                    old_rate = getattr(si_doc, 'conversion_rate', None)
                    si_doc.conversion_rate = float(ce_rate)
                    return {
                        'source': 'currency_exchange_table',
                        'rate': float(ce_rate),
                        'rate_date': check_date,
                        'old_rate': old_rate,
                        'posting_date': posting_date
                    }
        except Exception:
            pass
        
        return None  # Keep whatever rate ERPNext assigned

    @staticmethod
    def _discover_debit_to(si_doc):
        """Intelligently discover the correct debit_to (receivable) account.
        
        Follows Microsip/SAT per-customer account convention:
        - 1105.1.x = NACIONALES (ALL MXN) — domestic customers
        - 1105.2.x = EXTRANJEROS (ALL MXN) — international customers
        
        CRITICAL: ALL 1105.x accounts are in MXN (company currency).
        Even for USD invoices, the receivable account is MXN.
        ERPNext with "Allow Multi-Currency" enabled handles the conversion:
        - Invoice in USD → GL entries in MXN using conversion_rate
        - party_account_currency must be MXN (account currency), NOT invoice currency
        - When payment arrives at different exchange rate → exchange gain/loss
        
        This function also sets party_account_currency on the si_doc to match
        the resolved account's currency, preventing InvalidAccountCurrency errors.
        
        Resolution order:
        1. Search for a per-customer Microsip sub-account matching customer name
        2. Fall back to ERPNext get_party_account (canonical)
        3. Validate current debit_to is a valid Receivable ledger
        4. Search any Receivable ledger in the company
        5. Check customer's last submitted SI
        
        Args:
            si_doc: The Sales Invoice doc (before insert)
        
        Returns:
            str: The correct debit_to account name, or None if current is fine
        """
        current_debit_to = getattr(si_doc, 'debit_to', None)
        company = getattr(si_doc, 'company', None)
        customer = getattr(si_doc, 'customer', None)
        currency = getattr(si_doc, 'currency', None) or 'USD'
        
        def _is_valid_ledger(account_name):
            """Check if account is a valid non-group Receivable ledger."""
            try:
                info = frappe.db.get_value(
                    'Account', account_name,
                    ['is_group', 'account_currency', 'account_type'], as_dict=True
                )
                if not info or info.is_group:
                    return False
                if info.account_type != 'Receivable':
                    return False
                return info
            except Exception:
                return False
        
        def _set_party_account_currency(account_name):
            """Set party_account_currency on si_doc to match the account's currency.
            
            This is CRITICAL: party_account_currency must match the debit_to account's
            currency, NOT the invoice currency. For MXN Microsip accounts receiving
            USD invoices, party_account_currency = MXN.
            """
            try:
                acct_currency = frappe.db.get_value('Account', account_name, 'account_currency')
                if acct_currency:
                    si_doc.party_account_currency = acct_currency
            except Exception:
                pass
        
        # --- Strategy 1: Microsip/SAT per-customer sub-account ---
        # Convention: 1105.1.x = NACIONALES, 1105.2.x = EXTRANJEROS
        # ALL accounts under 1105 are MXN — even EXTRANJEROS
        # Each customer has their own ledger account named after them
        if customer and company:
            try:
                company_currency = frappe.db.get_value('Company', company, 'default_currency') or 'MXN'
                
                if currency != company_currency:
                    # Foreign currency invoice → search EXTRANJEROS first, then NACIONALES
                    parent_groups = ['1105.2 - EXTRANJEROS', '1105.1 - NACIONALES']
                else:
                    # Domestic currency invoice → search NACIONALES first, then EXTRANJEROS
                    parent_groups = ['1105.1 - NACIONALES', '1105.2 - EXTRANJEROS']
                
                # Clean customer name for matching — strip legal suffixes
                customer_clean = customer.upper().strip()
                for suffix in [' SA DE CV', ' S DE RL DE CV', ' S.A.', ' SA', ' AB',
                               ' LLC', ' INC', ' LTD', ' GMBH', ' SRL', ' SPR']:
                    customer_clean = customer_clean.replace(suffix, '')
                customer_clean = customer_clean.strip()
                
                for parent_prefix in parent_groups:
                    sub_accounts = frappe.get_all(
                        'Account',
                        filters={
                            'company': company,
                            'account_type': 'Receivable',
                            'is_group': 0,
                            'parent_account': ['like', f'{parent_prefix}%']
                        },
                        fields=['name', 'account_currency'],
                        limit_page_length=0
                    )
                    
                    # Exact-ish match: customer name appears in account name
                    for acct in sub_accounts:
                        acct_upper = acct.name.upper()
                        if customer_clean in acct_upper or customer.upper() in acct_upper:
                            _set_party_account_currency(acct.name)
                            return acct.name
                    
                    # Fuzzy: first significant word of customer name (min 4 chars)
                    words = [w for w in customer_clean.split() if len(w) >= 4]
                    if words:
                        primary_word = words[0]
                        for acct in sub_accounts:
                            if primary_word in acct.name.upper():
                                _set_party_account_currency(acct.name)
                                return acct.name
            except Exception:
                pass
        
        # --- Strategy 2: Use ERPNext's get_party_account (canonical) ---
        try:
            from erpnext.accounts.party import get_party_account
            resolved = get_party_account('Customer', customer, company)
            if resolved and _is_valid_ledger(resolved):
                _set_party_account_currency(resolved)
                return resolved
        except Exception:
            pass
        
        # --- Strategy 3: Validate current debit_to ---
        if current_debit_to and _is_valid_ledger(current_debit_to):
            _set_party_account_currency(current_debit_to)
            return None  # Current is fine, but ensure party_account_currency is set
        
        # --- Strategy 4: Find any Receivable ledger in the company ---
        try:
            accounts = frappe.get_all(
                'Account',
                filters={
                    'company': company,
                    'account_type': 'Receivable',
                    'is_group': 0
                },
                fields=['name', 'account_currency'],
                order_by='account_currency asc',  # Prefer company currency (MXN)
                limit_page_length=5
            )
            if accounts:
                _set_party_account_currency(accounts[0].name)
                return accounts[0].name
        except Exception:
            pass
        
        # --- Strategy 5: Look at customer's last submitted SI ---
        if customer:
            try:
                last_si = frappe.db.get_value(
                    'Sales Invoice',
                    {'customer': customer, 'docstatus': 1},
                    'debit_to',
                    order_by='posting_date desc'
                )
                if last_si and _is_valid_ledger(last_si):
                    _set_party_account_currency(last_si)
                    return last_si
            except Exception:
                pass
        
        return None  # Could not resolve — let ERPNext handle it

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
        # BUG15 fix: match SO-NNNNN prefix, resolve full name via DB
        so_match = re.search(r'(SAL-ORD-\d+-\d+|SO-\d{3,5})', query, re.IGNORECASE)
        if so_match:
            _so_prefix = so_match.group(1).upper()
            _so_full = frappe.db.get_value("Sales Order",
                {"name": ["like", f"{_so_prefix}%"], "docstatus": ["!=", 2]}, "name")
            if _so_full:
                class SOMatch:
                    def __init__(self, name):
                        self._name = name
                    def group(self, n=0):
                        return self._name
                so_match = SOMatch(_so_full)
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
        # Uses ERPNext's make_sales_invoice() which properly copies currency,
        # conversion_rate, taxes, payment_terms, debit_to, and all linked fields.
        # Then applies intelligent Mexico CFDI field discovery.
        #
        # POSTING DATE SUPPORT (migration):
        #   "invoice SO-XXXX date 2024-01-15" → sets posting_date to 2024-01-15
        #   Without date → defaults to today (nowdate)
        #   The posting_date drives the FIX T-1 exchange rate lookup.
        #   set_posting_time=1 tells ERPNext to respect our date instead of overriding.
        dn_match = re.search(r'(MAT-DN-\d+-\d+|DN-[^\s]+)', query, re.IGNORECASE)
        if (so_match or dn_match) and ("invoice" in query_lower or "factura" in query_lower):
            try:
                # --- Parse optional posting_date from command ---
                # Supports: "date 2024-01-15", "fecha 2024-01-15", "posting_date 2024-01-15"
                date_match = re.search(r'(?:date|fecha|posting_date)\s+(\d{4}-\d{2}-\d{2})', query, re.IGNORECASE)
                custom_posting_date = date_match.group(1) if date_match else None
                
                if dn_match:
                    dn_name = dn_match.group(1)
                    dn = frappe.get_doc("Delivery Note", dn_name)
                    # Discover CFDI fields from the DN (or its linked SO)
                    cfdi_fields = self._discover_mx_cfdi_fields(dn)
                    
                    if not is_confirm:
                        currency = dn.currency or "USD"
                        cfdi_info = f"\n  🇲🇽 CFDI: {cfdi_fields.get('mx_payment_option','?')} | Use: {cfdi_fields.get('mx_cfdi_use','?')} | Pay: {cfdi_fields.get('mode_of_payment','?')}"
                        date_info = f"\n  📅 Posting Date: {custom_posting_date}" if custom_posting_date else ""
                        return {
                            "requires_confirmation": True,
                            "preview": f"🧾 CREATE SALES INVOICE FROM {dn_name}?\n\n  Customer: {dn.customer}\n  Currency: {currency}\n  Total: {currency} {dn.grand_total:,.2f}{cfdi_info}{date_info}\n\nSay 'confirm' to proceed."
                        }
                    
                    from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice
                    si_dict = make_sales_invoice(dn_name)
                    # Inject CFDI fields into dict BEFORE creating doc
                    # (si.set() on custom Link fields can silently fail)
                    if hasattr(si_dict, 'update'):
                        si_dict.update(cfdi_fields)
                    elif isinstance(si_dict, dict):
                        si_dict.update(cfdi_fields)
                    si = frappe.get_doc(si_dict)
                    # Belt-and-suspenders: also set via attribute assignment
                    for field, value in cfdi_fields.items():
                        setattr(si, field, value)
                    # Apply custom posting_date if provided (migration scenario)
                    if custom_posting_date:
                        si.set_posting_time = 1
                        si.posting_date = custom_posting_date
                    # Fix debit_to: ensure it's a ledger matching SI currency
                    correct_debit_to = self._discover_debit_to(si)
                    if correct_debit_to:
                        si.debit_to = correct_debit_to
                    # Apply Banxico FIX T-1 exchange rate (uses posting_date for lookup)
                    fx_info = self._discover_conversion_rate(si)
                    # Set mx_product_service_key per item (CFDI 4.0 mandatory)
                    for item in si.items:
                        if not item.get("mx_product_service_key"):
                            psk = frappe.db.get_value("Item", item.item_code, "mx_product_service_key")
                            if psk:
                                item.mx_product_service_key = psk
                    si.insert()
                    site_name = frappe.local.site
                    fx_msg = ""
                    if fx_info:
                        fx_msg = f"\n  💱 TC: {fx_info['rate']} ({fx_info['source']}, FIX {fx_info.get('rate_date','')})"
                    date_msg = f"\n  📅 Date: {si.posting_date}" if custom_posting_date else ""
                    return {
                        "success": True,
                        "message": f"✅ Sales Invoice created: [{si.name}](https://{site_name}/app/sales-invoice/{si.name})\n  Customer: {si.customer}\n  Currency: {si.currency}\n  Total: {si.currency} {si.grand_total:,.2f}{date_msg}\n  🇲🇽 CFDI: {si.mx_payment_option} | Use: {si.mx_cfdi_use} | Pay: {si.mode_of_payment}{fx_msg}"
                    }
                elif so_match:
                    so_name = so_match.group(1)
                    so = frappe.get_doc("Sales Order", so_name)
                    # Discover CFDI fields from the SO
                    cfdi_fields = self._discover_mx_cfdi_fields(so)
                    
                    if not is_confirm:
                        currency = so.currency or "USD"
                        cfdi_info = f"\n  🇲🇽 CFDI: {cfdi_fields.get('mx_payment_option','?')} | Use: {cfdi_fields.get('mx_cfdi_use','?')} | Pay: {cfdi_fields.get('mode_of_payment','?')}"
                        date_info = f"\n  📅 Posting Date: {custom_posting_date}" if custom_posting_date else ""
                        return {
                            "requires_confirmation": True,
                            "preview": f"🧾 CREATE SALES INVOICE FROM {so_name}?\n\n  Customer: {so.customer}\n  Currency: {currency}\n  Total: {currency} {so.grand_total:,.2f}{cfdi_info}{date_info}\n\nSay 'confirm' to proceed."
                        }
                    
                    from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
                    si_dict = make_sales_invoice(so_name)
                    # Inject CFDI fields into dict BEFORE creating doc
                    # (si.set() on custom Link fields can silently fail)
                    if hasattr(si_dict, 'update'):
                        si_dict.update(cfdi_fields)
                    elif isinstance(si_dict, dict):
                        si_dict.update(cfdi_fields)
                    si = frappe.get_doc(si_dict)
                    # Belt-and-suspenders: also set via attribute assignment
                    for field, value in cfdi_fields.items():
                        setattr(si, field, value)
                    # Apply custom posting_date if provided (migration scenario)
                    if custom_posting_date:
                        si.set_posting_time = 1
                        si.posting_date = custom_posting_date
                    # Fix debit_to: ensure it's a ledger matching SI currency
                    correct_debit_to = self._discover_debit_to(si)
                    if correct_debit_to:
                        si.debit_to = correct_debit_to
                    # Apply Banxico FIX T-1 exchange rate (uses posting_date for lookup)
                    fx_info = self._discover_conversion_rate(si)
                    # Set mx_product_service_key per item (CFDI 4.0 mandatory)
                    for item in si.items:
                        if not item.get("mx_product_service_key"):
                            psk = frappe.db.get_value("Item", item.item_code, "mx_product_service_key")
                            if psk:
                                item.mx_product_service_key = psk
                    si.insert()
                    site_name = frappe.local.site
                    fx_msg = ""
                    if fx_info:
                        fx_msg = f"\n  💱 TC: {fx_info['rate']} ({fx_info['source']}, FIX {fx_info.get('rate_date','')})"
                    date_msg = f"\n  📅 Date: {si.posting_date}" if custom_posting_date else ""
                    return {
                        "success": True,
                        "message": f"✅ Sales Invoice created: [{si.name}](https://{site_name}/app/sales-invoice/{si.name})\n  Customer: {si.customer}\n  Currency: {si.currency}\n  Total: {si.currency} {si.grand_total:,.2f}{date_msg}\n  🇲🇽 CFDI: {si.mx_payment_option} | Use: {si.mx_cfdi_use} | Pay: {si.mode_of_payment}{fx_msg}"
                    }
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # ==================== END SALES-TO-PURCHASE CYCLE SOP ====================

        return None

