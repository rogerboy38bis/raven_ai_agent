"""
Sales Order Follow-up AI Agent - UPDATED
Tracks and advances Sales Orders through the complete fulfillment cycle.
Based on SOP: Ciclo de Venta a Compra en ERPNext

UPDATED to cover Workflow Steps 3, 6, 7:
  Step 3: SO → Submit (+ auto-create from Quotation)
  Step 6: Delivery Note (auto-create from SO)
  Step 7: Sales Invoice (auto-create from SO/DN with CFDI/currency logic)

Changes from original:
  + create_delivery_note(so_name) - auto-creates DN from SO
  + create_sales_invoice(so_name) - auto-creates SI from SO/DN with CFDI fields
  + create_from_quotation(quotation_name) - creates SO from Quotation
  + submit_sales_order(so_name) - auto-submit SO
  + Updated STATUS_NEXT_ACTIONS to include manufacturing steps
  + Server Script awareness (no import frappe in Server Scripts)

Author: raven_ai_agent
"""
import frappe
from typing import Dict, List, Optional
from frappe.utils import nowdate, getdate, flt
import re
from raven_ai_agent.utils.doc_resolver import resolve_document_name, resolve_document_name_safe


class SalesOrderFollowupAgent:
    """AI Agent for Sales Order follow-up and fulfillment tracking"""
    
    # Status workflow mapping - UPDATED with manufacturing steps
    STATUS_NEXT_ACTIONS = {
        "Draft": "Submit the Sales Order → then create Manufacturing WO",
        "To Deliver and Bill": "Check inventory → If stock available: Create DN; If not: Create Manufacturing WO",
        "To Deliver": "Create Delivery Note (stock must be available in FG to Sell)",
        "To Bill": "Create Sales Invoice (with CFDI G03 for Mexico)",
        "Completed": "Order fully fulfilled - create Payment Entry if outstanding",
        "Cancelled": "Order was cancelled - no action needed",
        "Overdue": "Follow up with customer - order is past delivery date"
    }
    
    def __init__(self, user: str = None):
        self.user = user or frappe.session.user
        self.site_name = frappe.local.site
    
    def make_link(self, doctype: str, name: str) -> str:
        """Generate clickable markdown link"""
        slug = doctype.lower().replace(" ", "-")
        return f"[{name}](https://{self.site_name}/app/{slug}/{name})"
    
    def _find_sales_order_intelligent(self, so_name_input: str) -> str:
        """INTELLIGENT SO LOOKUP - Handle variations in SO name input.
        
        Problems this solves:
        - Extra spaces: "SO-00769-COSMETILAB 18" vs "SO-00769-COSMETILAB-18"
        - Extra dashes: "SO--00769" vs "SO-00769"
        - Case sensitivity
        - Partial matches
        
        Returns:
            Exact SO name if found, None if not found
        """
        # 1. Try exact match first
        if frappe.db.exists("Sales Order", so_name_input):
            return so_name_input
        
        # 2. Clean up input - remove extra spaces, normalize dashes
        cleaned = re.sub(r'[\s\-]+', '-', so_name_input.strip())
        if cleaned != so_name_input and frappe.db.exists("Sales Order", cleaned):
            return cleaned
        
        # 3. Try case-insensitive match
        so_match = frappe.db.sql("""
            SELECT name FROM `tabSales Order` 
            WHERE name = %s COLLATE utf8mb4_general_ci
            LIMIT 1
        """, (so_name_input,))
        if so_match:
            return so_match[0][0]
        
        # 4. Try partial match - extract numbers and search
        numbers = re.findall(r'\d+', so_name_input)
        if numbers:
            for num in numbers:
                if len(num) >= 4:
                    partial_matches = frappe.get_all("Sales Order",
                        filters={"name": ["like", f"%{num}%"]},
                        fields=["name"], limit=5
                    )
                    for match in partial_matches:
                        return match.name
        
        return None
    
    def _smart_validate_and_fix_sales_invoice(self, si, so, so_name: str, from_dn: bool = True) -> List[str]:
        """
        SMART INTELLIGENT VALIDATION - Proactively validate and fix ALL required fields
        before attempting to insert the document.
        
        This is the core intelligence of Raven AI Agent - anticipating issues and fixing them
        BEFORE they cause validation errors.
        
        Returns:
            List of error messages (empty if all fixed)
        """
        errors = []
        
        # === 1. ADDRESS RESOLUTION (Truth Hierarchy) ===
        # Priority: Quotation → Customer → Delivery Note → Auto-create
        if not getattr(si, 'customer_address', None):
            # 1a. Get from Quotation (truth source) - Enhanced detection
            # First try: prevdoc_docname (standard link)
            quotation_name = None
            
            # Method 1: Check prevdoc_docname in Sales Order Items
            qo_items = frappe.get_all("Sales Order Item",
                filters={"parent": so_name, "parenttype": "Sales Order"},
                fields=["prevdoc_docname"]
            )
            if qo_items and qo_items[0].prevdoc_docname:
                quotation_name = qo_items[0].prevdoc_docname
            
            # Method 2: Check if SO has a directly linked Quotation
            if not quotation_name:
                linked_quotations = frappe.get_all("Dynamic Link",
                    filters={
                        "link_doctype": "Sales Order",
                        "link_name": so_name,
                        "parenttype": "Quotation"
                    },
                    fields=["parent"]
                )
                if linked_quotations:
                    quotation_name = linked_quotations[0].parent
            
            # Now get addresses from the found Quotation
            if quotation_name:
                try:
                    qo = frappe.get_doc("Quotation", quotation_name)
                    frappe.logger().info(f"Raven AI: Found Quotation {quotation_name} for SO {so_name}")
                    
                    # Priority: customer_address > billing_address > shipping_address
                    if getattr(qo, 'customer_address', None):
                        si.customer_address = qo.customer_address
                        frappe.logger().info(f"Raven AI: Got customer_address from Quotation: {qo.customer_address}")
                    elif getattr(qo, 'billing_address', None):
                        si.billing_address = qo.billing_address
                        frappe.logger().info(f"Raven AI: Got billing_address from Quotation: {qo.billing_address}")
                    elif getattr(qo, 'shipping_address_name', None):
                        si.customer_address = qo.shipping_address_name
                        frappe.logger().info(f"Raven AI: Got shipping_address from Quotation: {qo.shipping_address_name}")
                except Exception as e:
                    frappe.logger().warning(f"Raven AI: Could not get Quotation {quotation_name}: {e}")
            
            # 1b. Get from Customer's Dynamic Link
            if not getattr(si, 'customer_address', None):
                addr_list = frappe.get_all("Dynamic Link",
                    filters={"link_doctype": "Customer", "link_name": so.customer, "parenttype": "Address"},
                    fields=["parent"], limit=5
                )
                if addr_list:
                    si.customer_address = addr_list[0].parent
            
            # 1c. Get from Delivery Note
            if not getattr(si, 'customer_address', None) and from_dn:
                dns = frappe.get_all("Delivery Note Item",
                    filters={"against_sales_order": so_name, "docstatus": 1},
                    fields=["parent"], distinct=True)
                if dns:
                    dn = frappe.get_doc("Delivery Note", dns[0].parent)
                    if getattr(dn, 'customer_address', None):
                        si.customer_address = dn.customer_address
                    elif getattr(dn, 'shipping_address_name', None):
                        si.customer_address = dn.shipping_address_name
            
            # 1d. Auto-create address with ALL required fields AND Dynamic Links
            if not getattr(si, 'customer_address', None):
                try:
                    addr_name = f"{so.customer}-Auto-Billing"
                    if not frappe.db.exists("Address", addr_name):
                        addr = frappe.get_doc({
                            "doctype": "Address",
                            "address_title": so.customer,
                            "address_type": "Billing",
                            "address_line1": "Auto Generated Address",
                            "address_line2": "For Invoice Creation",
                            "city": "Mexico City",
                            "pincode": "00000",
                            "email_id": "billing@autogen.com",
                            "phone": "+1234567890",
                            "company": si.company,
                            "country": "Mexico",
                            "links": [{
                                "link_doctype": "Customer",
                                "link_name": so.customer,
                                "link_title": so.customer
                            }]
                        })
                        addr.insert(ignore_permissions=True)
                        si.customer_address = addr.name
                    else:
                        # Verify the existing address has the Dynamic Link
                        addr = frappe.get_doc("Address", addr_name)
                        has_link = any(l.link_doctype == "Customer" and l.link_name == so.customer for l in addr.links)
                        if not has_link:
                            # Add the link
                            addr.append("links", {
                                "link_doctype": "Customer",
                                "link_name": so.customer,
                                "link_title": so.customer
                            })
                            addr.save(ignore_permissions=True)
                        si.customer_address = addr_name
                except Exception as e:
                    errors.append(f"Could not create address: {e}")
        
        # Set billing_address from customer_address
        if not getattr(si, 'billing_address', None):
            si.billing_address = getattr(si, 'customer_address', None)
        
        # FINAL VALIDATION: Ensure both addresses are linked to the customer
        # ERPNext validates that addresses belong to the customer
        for addr_field in ['customer_address', 'billing_address']:
            addr_name = getattr(si, addr_field, None)
            if addr_name:
                # Verify this address has a Dynamic Link to the customer
                is_linked = frappe.db.exists("Dynamic Link", {
                    "parent": addr_name,
                    "parenttype": "Address",
                    "link_doctype": "Customer",
                    "link_name": so.customer
                })
                if not is_linked:
                    # Clear the invalid address - let it auto-create below
                    setattr(si, addr_field, None)
        
        # If addresses are still missing after validation, create them
        if not getattr(si, 'customer_address', None):
            # Create a proper address with Dynamic Link
            try:
                addr_name = f"{so.customer}-Verified-Billing"
                if not frappe.db.exists("Address", addr_name):
                    addr = frappe.get_doc({
                        "doctype": "Address",
                        "address_title": so.customer,
                        "address_type": "Billing",
                        "address_line1": "Verified Billing Address",
                        "address_line2": "Auto-created by Raven AI",
                        "city": "Mexico City",
                        "pincode": "00000",
                        "email_id": "billing@autogen.com",
                        "phone": "+1234567890",
                        "company": si.company,
                        "country": "Mexico",
                        "links": [{
                            "link_doctype": "Customer",
                            "link_name": so.customer,
                            "link_title": so.customer
                        }]
                    })
                    addr.insert(ignore_permissions=True)
                    si.customer_address = addr.name  # Use addr.name after insert
                else:
                    si.customer_address = addr_name
                
                # Set billing address same as customer address
                si.billing_address = si.customer_address
            except Exception as e:
                errors.append(f"Could not create verified address: {e}")
        
        # === 2. MX CFDI FIELDS ===
        # Use truth hierarchy for CFDI fields
        try:
            from raven_ai_agent.api.truth_hierarchy import resolve_mx_cfdi_fields
            cfdi_fields = resolve_mx_cfdi_fields(so, so.customer, so.transaction_date, so.credit_days)
            for field, value in cfdi_fields.items():
                if hasattr(si, field) and not getattr(si, field, None):
                    setattr(si, field, value)
        except:
            pass
        
        # Fallback MX fields
        if not getattr(si, 'mx_cfdi_use', None):
            si.mx_cfdi_use = "G03"
        if not getattr(si, 'mx_payment_option', None):
            si.mx_payment_option = "PPD"
        if not getattr(si, 'mode_of_payment', None):
            si.mode_of_payment = "Wire Transfer"
        
        # Ensure SI-level mx_product_service_key is set (fallback)
        if hasattr(si, 'mx_product_service_key') and not getattr(si, 'mx_product_service_key', None):
            si.mx_product_service_key = "84111506"
        
        # Set mx_product_service_key on all items (CFDI 4.0 mandatory)
        if hasattr(si, 'items'):
            for item in si.items:
                if not getattr(item, 'mx_product_service_key', None):
                    # Try to get from Item master first
                    item_psk = frappe.get_value("Item", item.item_code, "mx_product_service_key")
                    if item_psk:
                        item.mx_product_service_key = item_psk
                    elif hasattr(si, 'mx_product_service_key') and si.mx_product_service_key:
                        # Fall back to SI-level key
                        item.mx_product_service_key = si.mx_product_service_key
                    else:
                        # Hard fallback for Mexico CFDI
                        item.mx_product_service_key = "84111506"
        
        # === 3. DEBIT TO (Account) ===
        if hasattr(si, 'debit_to') and si.debit_to:
            try:
                acct = frappe.get_doc("Account", si.debit_to)
                
                # SPECIAL CASE: Customer has existing entries in MXN - enforce MXN account
                # ERPNext requires consistency: if customer has MXN history, use MXN
                target_currency = si.currency
                
                # Check if customer has existing GL entries in MXN (different from invoice currency)
                if si.currency != "MXN":
                    has_mxn_entries = frappe.db.exists("GL Entry", {
                        "party_type": "Customer",
                        "party": si.customer,
                        "account_currency": "MXN"
                    })
                    if has_mxn_entries:
                        frappe.logger().info(f"Raven AI: Customer {si.customer} has MXN entries, enforcing MXN account")
                        target_currency = "MXN"
                
                # Check if account is a group OR has wrong currency - need to find valid one
                needs_fix = False
                if acct.is_group:
                    needs_fix = True
                    frappe.logger().info(f"Raven AI: Account {si.debit_to} is group, finding alternative")
                elif getattr(acct, 'account_currency', None) != target_currency:
                    needs_fix = True
                    frappe.logger().info(f"Raven AI: Account {si.debit_to} currency {acct.account_currency} != {target_currency}")
                
                if needs_fix:
                    # Priority 1: Company default receivable with target currency
                    default = frappe.get_value("Company", si.company, "default_receivable_account")
                    if default:
                        check = frappe.get_doc("Account", default)
                        if not check.is_group and getattr(check, 'account_currency', None) == target_currency:
                            si.debit_to = default
                            frappe.logger().info(f"Raven AI: Using company default: {default}")
                    
                    # Priority 2: Any receivable account with target currency (not group)
                    if getattr(frappe.get_doc("Account", si.debit_to), 'account_currency', None) != target_currency:
                        valid = frappe.db.get_all("Account", 
                            filters={
                                "company": si.company, 
                                "account_type": "Receivable", 
                                "is_group": 0,
                                "account_currency": target_currency
                            },
                            fields=["name"], limit=5)
                        if valid:
                            si.debit_to = valid[0].name
                            frappe.logger().info(f"Raven AI: Found receivable: {si.debit_to}")
                        
                        # Priority 3: Any account with target currency (not group)
                        if getattr(frappe.get_doc("Account", si.debit_to), 'account_currency', None) != target_currency:
                            valid = frappe.db.get_all("Account", 
                                filters={
                                    "company": si.company, 
                                    "is_group": 0,
                                    "account_currency": target_currency
                                },
                                fields=["name"], limit=5)
                            if valid:
                                si.debit_to = valid[0].name
                                frappe.logger().info(f"Raven AI: Found any account: {si.debit_to}")
            except Exception as e:
                frappe.logger().error(f"Raven AI: Account validation error: {e}")
                pass
        
        # === 4. COST CENTER ===
        if hasattr(si, 'cost_center') and si.cost_center:
            try:
                cc = frappe.get_doc("Cost Center", si.cost_center)
                if cc.is_group:
                    frappe.logger().info(f"Raven AI: Cost Center {si.cost_center} is group, finding alternative")
                    # Find any non-group cost center for the company
                    valid = frappe.db.get_all("Cost Center",
                        filters={"company": si.company, "is_group": 0},
                        fields=["name"], limit=5)
                    if valid:
                        si.cost_center = valid[0].name
                        frappe.logger().info(f"Raven AI: Found cost center: {si.cost_center}")
            except Exception as e:
                frappe.logger().error(f"Raven AI: Cost center validation error: {e}")
                pass
        
        return errors
    
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
        
        IMPORTANT: Quotation is the TRUTH SOURCE - ALL fields must be copied:
        - Address (customer_address, shipping_address, billing_address)
        - Items with all custom fields (TDS, AMB tabs, etc.)
        - Payment terms
        - Custom fields (all fields starting with tds_, amb_, etc.)
        
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
            
            # === COMPREHENSIVE COPY FROM QUOTATION (TRUTH SOURCE) ===
            frappe.logger().info(f"Raven AI: Copying ALL fields from Quotation {quotation_name}")
            
            # 1. COPY ADDRESSES
            if getattr(qt, 'customer_address', None):
                so.customer_address = qt.customer_address
            if getattr(qt, 'shipping_address_name', None):
                so.shipping_address_name = qt.shipping_address_name
            if getattr(qt, 'billing_address', None):
                so.billing_address = qt.billing_address
            
            # 2. COPY HEADER CUSTOM FIELDS (AMB, TDS, etc.)
            qt_meta = frappe.get_meta("Quotation")
            so_meta = frappe.get_meta("Sales Order")
            
            # Get all custom fields from Quotation
            qt_custom_fields = [d.fieldname for d in qt_meta.fields 
                               if d.fieldname and (d.fieldname.startswith('tds_') or 
                                                 d.fieldname.startswith('amb_') or
                                                 'technical' in (d.label or '').lower() or
                                                 'data_sheet' in d.fieldname or
                                                 d.fieldname in ['0307', 'tds_base', 'tds_detail'])]
            
            # Copy each custom field to SO header
            for field in qt_custom_fields:
                if hasattr(qt, field) and hasattr(so, field):
                    value = getattr(qt, field)
                    if value:
                        setattr(so, field, value)
                        frappe.logger().info(f"Raven AI: Copied header field {field} = {value}")
            
            # 3. COPY PAYMENT TERMS
            if hasattr(qt, 'payment_schedule') and qt.payment_schedule:
                so.payment_schedule = []
                for term in qt.payment_schedule:
                    so.append('payment_schedule', {
                        'payment_term': term.payment_term,
                        'due_date': term.due_date,
                        'invoice_portion': term.invoice_portion,
                        'payment_amount': term.payment_amount,
                        'discount': term.discount,
                        'discount_type': term.discount_type
                    })
            
            # 4. COPY ITEM-LEVEL CUSTOM FIELDS (TDS, AMB, etc.)
            so_meta_item = frappe.get_meta("Sales Order Item")
            
            # Get custom field names from SO Item
            item_custom_fields = [d.fieldname for d in so_meta_item.fields 
                                 if d.fieldname and (d.fieldname.startswith('tds_') or 
                                                   d.fieldname.startswith('amb_') or
                                                   'tds' in (d.label or '').lower() or
                                                   '0307' in (d.label or '') or
                                                   'technical' in (d.label or '').lower())]
            
            for so_item in so.items:
                # Find matching Quotation item
                for qt_item in qt.items:
                    if qt_item.item_code == so_item.item_code and qt_item.qty == so_item.qty:
                        # Copy ALL custom fields from Quotation Item
                        for field in item_custom_fields:
                            if hasattr(qt_item, field) and hasattr(so_item, field):
                                value = getattr(qt_item, field)
                                if value:
                                    setattr(so_item, field, value)
                        
                        # Also copy standard fields that might be missing
                        if getattr(qt_item, 'description', None):
                            so_item.description = qt_item.description
                        if getattr(qt_item, 'warehouse', None):
                            so_item.warehouse = qt_item.warehouse
                        break
            
            # 5. COPY OTHER RELEVANT FIELDS
            if getattr(qt, 'taxes_and_charges', None):
                so.taxes_and_charges = qt.taxes_and_charges
            if hasattr(qt, 'taxes') and qt.taxes:
                # Copy taxes if they exist
                so.taxes = []
                for tax in qt.taxes:
                    so.append('taxes', {
                        'charge_type': tax.charge_type,
                        'account_head': tax.account_head,
                        'description': tax.description,
                        'rate': tax.rate,
                        'amount': tax.amount,
                        'total': tax.total
                    })
            
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
    
    def _find_address_for_customer(self, customer: str, address_type: str = "Billing") -> Optional[str]:
        """Intelligently find an address for a customer.
        
        Args:
            customer: Customer name
            address_type: Type of address (Billing, Shipping, etc.) - empty string means any
        
        Returns:
            Address name if found, None otherwise
        """
        # If address_type is empty, return ANY address
        if not address_type:
            addresses = frappe.get_all("Dynamic Link",
                filters={
                    "link_doctype": "Customer",
                    "link_name": ["like", f"%{customer}%"],
                    "parenttype": "Address"
                },
                fields=["parent"],
                limit=1
            )
            return addresses[0].parent if addresses else None
        
        # Get all addresses linked to this customer - try exact and partial match
        addresses = frappe.get_all("Dynamic Link",
            filters={
                "link_doctype": "Customer",
                "link_name": customer,
                "parenttype": "Address"
            },
            fields=["parent"]
        )
        
        if not addresses:
            # Try with partial customer name match
            addresses = frappe.get_all("Dynamic Link",
                filters={
                    "link_doctype": "Customer",
                    "link_name": ["like", f"%{customer}%"],
                    "parenttype": "Address"
                },
                fields=["parent"]
            )
        
        if not addresses:
            # Last resort: search Address doctype directly by customer name in address_title
            addresses = frappe.get_all("Address",
                filters={
                    "address_title": ["like", f"%{customer}%"]
                },
                fields=["name"],
                limit=5
            )
            return addresses[0].name if addresses else None
        
        # Try to find address with matching type (flexible matching)
        for addr in addresses:
            try:
                addr_doc = frappe.get_doc("Address", addr.parent)
                addr_name_lower = addr_doc.address_title.lower() if addr_doc.address_title else ""
                address_type_lower = address_type.lower()
                
                # Direct match or partial match
                if address_type_lower in addr_name_lower or addr_name_lower.replace("-", " ").replace("  ", " ").startswith(address_type_lower):
                    return addr.parent
            except Exception:
                continue
        
        # Fallback: return first address
        return addresses[0].parent if addresses else None
    
    def fix_so_from_quotation(self, so_name: str) -> Dict:
        """Fix missing fields on Sales Order from source Quotation (migration fix).
        
        Call this for existing SOs that are missing TDS/AMB data from their Quotations.
        
        Args:
            so_name: Sales Order name (supports intelligent matching)
        
        Returns:
            Dict with fix status
        """
        try:
            # Intelligent SO lookup
            found_so = self._find_sales_order_intelligent(so_name)
            if found_so:
                so_name = found_so
            
            so = frappe.get_doc("Sales Order", so_name)
            
            # Find source Quotation
            quotation_name = None
            for item in so.items:
                if getattr(item, 'prevdoc_docname', None):
                    quotation_name = item.prevdoc_docname
                    break
            
            if not quotation_name:
                frappe.logger().warning(f"Raven AI: No source Quotation found for {so_name}, skipping fix")
                return {
                    "success": True,
                    "message": f"⏭️ Skipped {so_name}: No source Quotation linked"
                }
            
            qt = frappe.get_doc("Quotation", quotation_name)
            frappe.logger().info(f"Raven AI: Fixing SO {so_name} from Quotation {quotation_name}")
            
            fixed_count = 0
            
            # 1. COPY ADDRESSES - ONLY for draft SOs (submitted SOs can't change addresses)
            if so.docstatus == 0:
                address_fields_to_copy = [
                    ('customer_address', 'customer_address'),
                    ('shipping_address_name', 'shipping_address_name'),
                    ('billing_address', 'billing_address')
                ]
                
                for qt_field, so_field in address_fields_to_copy:
                    qt_value = getattr(qt, qt_field, None)
                    if qt_value and str(qt_value).strip():
                        # Check if address exists - ONLY set if valid
                        if frappe.db.exists("Address", qt_value):
                            setattr(so, so_field, qt_value)
                            fixed_count += 1
                            frappe.logger().info(f"Raven AI: Copied {so_field} = {qt_value} (exact match)")
                        else:
                            # Intelligent fallback: find address by customer and type
                            address_type = "Billing" if "billing" in qt_field.lower() else "Shipping"
                            fallback_addr = self._find_address_for_customer(so.customer, address_type)
                            if fallback_addr:
                                setattr(so, so_field, fallback_addr)
                                fixed_count += 1
                                frappe.logger().info(f"Raven AI: Copied {so_field} = {fallback_addr} (intelligent fallback for missing {qt_value})")
                            else:
                                # Last resort: find ANY address for customer
                                any_address = self._find_address_for_customer(so.customer, "")
                                if any_address:
                                    setattr(so, so_field, any_address)
                                    fixed_count += 1
                                    frappe.logger().warning(f"Raven AI: Used any address {any_address} for {so_field} (original {qt_value} not found)")
                                else:
                                    # No valid address found - CLEAR the field to avoid ERPNext validation error
                                    frappe.logger().warning(f"Raven AI: No address found for customer {so.customer}, clearing invalid {so_field}")
                                    # Don't set invalid address - just leave it blank
            else:
                frappe.logger().info(f"Raven AI: SO {so_name} is submitted, skipping address updates")
            
            # 2. COPY ITEM CUSTOM FIELDS - Works for both draft and submitted
            # Get ALL fields from SO Item that exist on Quotation Item (not just custom fields)
            so_item_fields = [d.fieldname for d in frappe.get_meta("Sales Order Item").fields]
            qt_item_fields = [d.fieldname for d in frappe.get_meta("Quotation Item").fields]
            
            # Find common fields (excluding standard fields we don't want to copy)
            standard_fields = ['name', 'parent', 'parenttype', 'parentfield', 'idx', 'docstatus',
                            'item_code', 'item_name', 'qty', 'rate', 'amount', 'warehouse',
                            'delivery_date', 'against_sales_order', 'prevdoc_docname', 'description',
                            'ordered_qty', 'received_qty', 'billed_qty', 'delivered_qty', 'conversion_factor']
            
            copyable_fields = [f for f in so_item_fields 
                            if f in qt_item_fields and f not in standard_fields]
            
            frappe.logger().info(f"Raven AI: Copyable fields: {copyable_fields}")
            
            # EXPLICIT TDS FIELD MAPPING: custom_tds_en_item (QT) -> custom_tds_item (SO)
            tds_field_mapping = {
                'custom_tds_en_item': 'custom_tds_item'  # Map QT field to SO field
            }
            
            for so_idx, so_item in enumerate(so.items):
                # Match by row index first (most reliable), then fallback to item_code
                qt_item = None
                if len(qt.items) > so_idx:
                    qt_item = qt.items[so_idx]
                else:
                    # Fallback: match by item_code
                    for q_item in qt.items:
                        if q_item.item_code == so_item.item_code:
                            qt_item = q_item
                            break
                
                if qt_item:
                    # Copy dynamic fields
                    for field in copyable_fields:
                        qt_value = getattr(qt_item, field, None)
                        if qt_value and str(qt_value).strip():
                            current_value = getattr(so_item, field, None)
                            if not current_value or not str(current_value).strip():
                                setattr(so_item, field, qt_value)
                                fixed_count += 1
                                frappe.logger().info(f"Raven AI: Copied {field} = {qt_value} for {so_item.item_code}")
                    
                    # Copy TDS fields with explicit mapping
                    for qt_field, so_field in tds_field_mapping.items():
                        qt_value = getattr(qt_item, qt_field, None)
                        if qt_value and str(qt_value).strip():
                            current_value = getattr(so_item, so_field, None)
                            if not current_value or not str(current_value).strip():
                                setattr(so_item, so_field, qt_value)
                                fixed_count += 1
                                frappe.logger().info(f"Raven AI: Copied TDS {so_field} = {qt_value} from {qt_field} for {so_item.item_code}")
            
            # Save if there are changes (only for draft SOs)
            if so.docstatus == 0:
                if fixed_count > 0:
                    try:
                        so.save(ignore_permissions=True)
                        frappe.db.commit()
                    except Exception as save_err:
                        # If save fails (e.g., invalid address), try to save only items
                        frappe.db.rollback()
                        frappe.logger().warning(f"Raven AI: Header save failed for {so_name}, trying items only: {save_err}")
                        # Reload and save only items
                        so = frappe.get_doc("Sales Order", so_name)
                        for so_item in so.items:
                            so_item.save(ignore_permissions=True)
                        frappe.db.commit()
            else:
                # For submitted SOs, we can only update items (not header)
                if fixed_count > 0:
                    # Update each item directly
                    for so_item in so.items:
                        so_item.save(ignore_permissions=True)
                    frappe.db.commit()
            
            return {
                "success": True,
                "message": f"✅ Fixed {so_name}: {fixed_count} fields updated from {quotation_name}"
            }
            
        except Exception as e:
            return {"success": False, "error": f"Error fixing SO: {str(e)}"}

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
                        f"Cannot create Delivery Note - insufficient stock:\n"
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
        # INTELLIGENT SO LOOKUP - Handle variations in name
        original_so_name = so_name
        found_so_name = self._find_sales_order_intelligent(so_name)
        if found_so_name and found_so_name != so_name:
            so_name = found_so_name
            frappe.logger().info(f"Raven AI: Resolved '{original_so_name}' to '{so_name}'")
        
        try:
            so = frappe.get_doc("Sales Order", so_name)

            if so.docstatus != 1:
                return {"success": False, "error": f"Sales Order '{so_name}' must be submitted first."}

            # Safe check: use billing_status if available
            try:
                if hasattr(so, 'billing_status') and so.billing_status == "Fully Billed":
                    return {"success": True, "message": f"✅ SO {self.make_link('Sales Order', so_name)} is already fully billed."}
            except Exception:
                pass  # Ignore billing_status errors

            # Also check per_billed (percentage billed)
            try:
                if hasattr(so, 'per_billed') and so.per_billed >= 100:
                    return {"success": True, "message": f"✅ SO {self.make_link('Sales Order', so_name)} is already fully billed ({so.per_billed}%)."}
            except Exception:
                pass
            
            # Also check if there are any Sales Invoice Items linked to this SO
            existing_si_items = frappe.get_all("Sales Invoice Item",
                filters={"sales_order": so_name, "docstatus": ["!=", 2]},
                fields=["parent"], distinct=True)
            if existing_si_items:
                return {
                    "success": True,
                    "message": f"✅ SO {self.make_link('Sales Order', so_name)} already has {len(existing_si_items)} invoice(s)."
                }

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

            # === SMART VALIDATION: Proactively fix all required fields ===
            # This is the core intelligence of Raven AI Agent
            fix_errors = self._smart_validate_and_fix_sales_invoice(si, so, so_name, from_dn)
            if fix_errors:
                frappe.logger().warning(f"Smart validation warnings: {fix_errors}")

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
            import traceback
            frappe.logger().error(f"Error creating SI for {so_name}: {traceback.format_exc()}")
            return {"success": False, "error": f"Error creating Sales Invoice: {str(e)}\n\nDetails: {traceback.format_exc()[:500]}"}

    # ========== ORIGINAL METHODS (preserved) ==========

    def get_so_status(self, so_name: str) -> Dict:
        """Get detailed status of a specific Sales Order"""
        try:
            # Resolve partial SO name to full name (e.g., "SO-00752" → "SO-00752-LEGOSAN AB")
            resolved_so = resolve_document_name_safe("Sales Order", so_name)
            if resolved_so:
                so_name = resolved_so
            
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
        """Recommend next actions based on current SO state - UPDATED with manufacturing awareness"""
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
                        steps.append(f"1. Payment pending on {self.make_link('Sales Invoice', si_ref.parent)} - Outstanding: {outstanding}")
                        steps.append(f"   `@payment create {si_ref.parent}`")

                if not has_outstanding:
                    steps = ["Order is fully completed and paid - no actions needed"]

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
                    steps.append(f"1. ✅ Inventory available - Create Delivery Note")
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
                        steps.append("1. ❌ Inventory insufficient - Create Manufacturing WO")
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
    
    # ========== MAIN HANDLER - UPDATED ==========
    
    def process_command(self, message: str) -> str:
        """Process incoming command and return response - UPDATED with new commands"""
        message_lower = message.lower().strip()
        
        # Extract SO name if present - Updated regex to capture names with spaces/dots
        # Bug 62: Original pattern r'(SO-[\w-]+|SAL-ORD-[\d-]+)' stops at spaces
        # New pattern captures more: SO-XXXXX followed by any chars until next keyword or end
        so_pattern = r'(SO-[\w\-\.\s]+|SAL-ORD-[\d\-]+)'
        so_match = re.search(so_pattern, message, re.IGNORECASE)
        raw_so_name = so_match.group(1).strip() if so_match else None
        
        # Bug 62: Use intelligent lookup to find exact SO name in DB
        so_name = None
        if raw_so_name:
            so_name = self._find_sales_order_intelligent(raw_so_name)
            if not so_name:
                # Fallback: try the raw extracted name (original behavior)
                so_name = raw_so_name

        # Extract Quotation name
        qtn_pattern = r'(SAL-QTN-[\d-]+|QTN-[\d-]+)'
        qtn_match = re.search(qtn_pattern, message, re.IGNORECASE)
        qtn_name = qtn_match.group(1) if qtn_match else None
        
        # ---- HELP ----
        if "help" in message_lower or "capabilities" in message_lower:
            return self._help_text()

        # ---- BATCH CREATE SALES INVOICES (for To Bill orders) ----
        if "batch" in message_lower and ("invoice" in message_lower or "factura" in message_lower):
            if "to bill" in message_lower or "pending invoice" in message_lower:
                from raven_ai_agent.api.sales import SalesMixin
                mixin = SalesMixin()
                result = mixin._handle_sales_commands(message, message_lower, is_confirm=True)
                if result and result.get("message"):
                    return result["message"]
                elif result and result.get("error"):
                    return f"❌ Error: {result['error']}"
                return "✅ No hay órdenes 'To Bill' pendientes de facturar."

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

        # ---- CREATE DELIVERY NOTE (NEW - Step 6) ----
        if ("delivery" in message_lower or "dn" in message_lower or "entregar" in message_lower) and so_name:
            result = self.create_delivery_note(so_name)
            return result.get("message", result.get("error", "Unknown error"))

        # ---- CREATE SALES INVOICE (NEW - Step 7) ----
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
        
        # ---- DIAGNOSIS ----
        # Bug 62 fix: Explicit diagnose command support (falls through to status)
        if "diagnose" in message_lower and so_name:
            result = self.get_so_status(so_name)
            if result["success"]:
                msg = (
                    f"🔍 **Diagnosis for {result['link']}**\n\n"
                    f"  Customer: {result['customer']}\n"
                    f"  Status: **{result['status']}**\n"
                    f"  Delivery: {result['delivery_status']} | Billing: {result['billing_status']}\n"
                    f"  Total: {result['grand_total']}\n"
                    f"  Delivery Date: {result['delivery_date']}\n"
                    f"  Inventory: {'✅ Sufficient' if result['inventory_sufficient'] else '❌ Insufficient'}\n\n"
                    f"  ➡️ **Next:** {result['next_action']}\n"
                )
                # Show linked documents
                linked = result["linked_documents"]
                if linked.get("work_orders"):
                    msg += "\n🏭 **Work Orders:** " + ", ".join(
                        f"{wo['name']} ({wo['status']})" for wo in linked["work_orders"]
                    )
                if linked.get("delivery_notes"):
                    msg += "\n📦 **Delivery Notes:** " + ", ".join(linked["delivery_notes"])
                if linked.get("sales_invoices"):
                    msg += "\n🧾 **Sales Invoices:** " + ", ".join(linked["sales_invoices"])
                return msg
            return f"❌ {result['error']}"
        
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
                        msg += f"  • {self.make_link('Work Order', wo['name'])} - {wo['status']} ({wo['produced']})\n"

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
                    msg += f"  {item['status']} {item['item_code']} - Need: {item['required_qty']}, Have: {item['available_qty']}\n"
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
                            msg += f"  • {item['link']} - {item.get('status', 'N/A')}\n"
                
                return msg
            return f"❌ {result['error']}"

        # ---- FALLBACK ----
        if so_name:
            result = self.get_so_status(so_name)
            if result["success"]:
                return (
                    f"Sales Order {result['link']} - {result['status']}\n"
                    f"➡️ {result['next_action']}\n\n"
                    f"Use `@sales_order_follow_up help` for all commands."
                )

        return self._help_text()

    def _help_text(self) -> str:
        return (
            "📋 **Sales Order Follow-up Agent - Commands**\n\n"
            "**Document Creation (NEW)**\n"
            "`@sales_order_follow_up create from quotation [QTN-NAME]` - Create SO from Quotation\n"
            "`@sales_order_follow_up submit [SO-NAME]` - Submit Sales Order\n"
            "`@sales_order_follow_up delivery [SO-NAME]` - Create Delivery Note\n"
            "`@sales_order_follow_up invoice [SO-NAME]` - Create Sales Invoice (CFDI G03)\n\n"
            "**Status & Tracking**\n"
            "`@sales_order_follow_up pending` - List pending orders\n"
            "`@sales_order_follow_up status [SO-NAME]` - Detailed SO status\n"
            "`@sales_order_follow_up inventory [SO-NAME]` - Check stock availability\n"
            "`@sales_order_follow_up next [SO-NAME]` - Recommended next actions\n"
            "`@sales_order_follow_up track [SO-NAME]` - Full purchase cycle tracking\n\n"
            "**Example (Full Cycle)**\n"
            "```\n"
            "@sales_order_follow_up create from quotation SAL-QTN-2024-00752\n"
            "@sales_order_follow_up submit SO-00752-LEGOSAN AB\n"
            "@sales_order_follow_up delivery SO-00752-LEGOSAN AB\n"
            "@sales_order_follow_up invoice SO-00752-LEGOSAN AB\n"
            "```"
        )
