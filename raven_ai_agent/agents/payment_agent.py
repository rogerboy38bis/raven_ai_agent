"""
Payment AI Agent
Handles Payment Entry creation and reconciliation from Sales Invoices.

Covers Workflow Step 8:
  Step 8: Payment Entry from Sales Invoice

Key Intelligence:
  - Creates Payment Entry from submitted Sales Invoice
  - Handles multi-currency (USD sales with MXN company)
  - Applies Banxico FIX T-1 exchange rate at payment date
  - Calculates exchange gain/loss (ganancia/pérdida cambiaria)
  - Reconciles Payment Entry with Sales Invoice
  - Tracks outstanding amounts
  - CFDI compliance awareness

Exchange Gain/Loss Flow (per Luis P AMB):
  Invoice: USD 10,000 × TC_invoice 17.26 = MXN 172,600 (CxC)
  Payment: USD 10,000 × TC_payment 17.60 = MXN 176,000 (received)
  Difference: MXN 3,400 → Utilidad cambiaria (Exchange Gain)
  If TC_payment < TC_invoice → Pérdida cambiaria (Exchange Loss)

Author: raven_ai_agent
"""
import frappe
import re
from typing import Dict, List, Optional
from frappe.utils import nowdate, getdate, flt
from raven_ai_agent.utils.doc_resolver import resolve_document_name_safe


class PaymentAgent:
    """AI Agent for payment operations: Payment Entries and reconciliation"""

    PAYMENT_STATUS_MAP = {
        "Draft": "Submit the Payment Entry",
        "Submitted": "Payment recorded — verify bank reconciliation",
        "Cancelled": "Payment was cancelled — no action needed"
    }

    def __init__(self, user: str = None):
        self.user = user or frappe.session.user
        self.site_name = frappe.local.site

    def make_link(self, doctype: str, name: str) -> str:
        """Generate clickable markdown link for ERPNext documents"""
        slug = doctype.lower().replace(" ", "-")
        return f"[{name}](https://{self.site_name}/app/{slug}/{name})"

    def _trace_to_quotation(self, payment_entry) -> Optional[object]:
        """Trace from Payment Entry -> Sales Invoice -> Sales Order -> Quotation.
        
        Returns the Quotation doc if found, None otherwise.
        """
        try:
            # Get the first Sales Invoice reference
            for ref in payment_entry.references:
                if ref.reference_doctype == "Sales Invoice":
                    si_name = ref.reference_name
                    si = frappe.get_doc("Sales Invoice", si_name)
                    
                    # Trace SI -> SO -> QTN
                    for item in si.items or []:
                        so_name = getattr(item, 'sales_order', None)
                        if so_name:
                            so = frappe.get_doc("Sales Order", so_name)
                            # Trace SO -> QTN
                            for so_item in so.items or []:
                                qtn_name = getattr(so_item, 'prevdoc_docname', None)
                                if qtn_name:
                                    return frappe.get_doc("Quotation", qtn_name)
        except Exception:
            pass
        return None

    def _ensure_customer_address_and_contact(self, pe: object) -> Dict:
        """Pre-flight check: Ensure Customer has primary address and contact.
        
        If Customer is missing customer_primary_address or customer_primary_contact,
        trace back through the payment chain (PE -> SI -> SO -> QTN) to find them.
        
        Returns:
            Dict with 'success' (bool), 'fixed' (list of what was fixed), 'error' (if any)
        """
        try:
            # Get customer from payment entry
            customer_name = pe.party
            if not customer_name:
                return {"success": True, "fixed": [], "error": None}  # Nothing to fix
            
            customer_doc = frappe.get_doc("Customer", customer_name)
            
            fixed = []
            errors = []
            
            # Check if customer_primary_address is set
            if not getattr(customer_doc, 'customer_primary_address', None):
                # Trace to find address from Quotation
                qtn = self._trace_to_quotation(pe)
                if qtn and getattr(qtn, 'customer_address', None):
                    customer_doc.customer_primary_address = qtn.customer_address
                    fixed.append(f"customer_primary_address -> {qtn.customer_address}")
                else:
                    errors.append("Customer Primary Address not found in linked Quotation")
            
            # Check if customer_primary_contact is set
            if not getattr(customer_doc, 'customer_primary_contact', None):
                # Trace to find contact from Quotation
                qtn = self._trace_to_quotation(pe)
                if qtn and getattr(qtn, 'contact_person', None):
                    customer_doc.customer_primary_contact = qtn.contact_person
                    fixed.append(f"customer_primary_contact -> {qtn.contact_person}")
                else:
                    # Try getting from Sales Invoice directly
                    for ref in pe.references:
                        if ref.reference_doctype == "Sales Invoice":
                            si = frappe.get_doc("Sales Invoice", ref.reference_name)
                            if getattr(si, 'contact_person', None):
                                customer_doc.customer_primary_contact = si.contact_person
                                fixed.append(f"customer_primary_contact -> {si.contact_person}")
                                break
            
            # Save if we made changes
            if fixed:
                customer_doc.save(ignore_permissions=True)
                frappe.db.commit()
            
            if errors and not fixed:
                # Construct helpful error message
                customer_link = self.make_link("Customer", customer_name)
                error_msg = (
                    f"Cannot submit payment: Customer {customer_link} has no Primary Address. "
                    f"Address not found in the linked Quotation/Sales Order/Sales Invoice chain either. "
                    f"Please set the address manually at: {customer_link}"
                )
                return {"success": False, "fixed": fixed, "error": error_msg}
            
            return {"success": True, "fixed": fixed, "error": None}
            
        except frappe.DoesNotExistError:
            return {"success": True, "fixed": [], "error": None}  # Customer doesn't exist, let ERPNext handle it
        except Exception as e:
            return {"success": True, "fixed": [], "error": None}  # Don't block on errors, let ERPNext handle

    # ========== PAYMENT ENTRY OPERATIONS (Step 8) ==========

    def create_payment_entry(self, si_name: str, amount: float = None,
                             mode_of_payment: str = None,
                             payment_date: str = None,
                             payment_form: str = None) -> Dict:
        """Create a Payment Entry from a Sales Invoice.
        
        Applies Banxico FIX T-1 exchange rate for the payment date.
        If the payment rate differs from invoice rate, calculates
        exchange gain/loss and adds it to the Payment Entry deductions.
        
        Args:
            si_name: Sales Invoice name
            amount: Payment amount in invoice currency. If None, uses full outstanding.
            mode_of_payment: Mode of payment (e.g. 'Wire Transfer', 'Cash')
            payment_date: Payment posting date (YYYY-MM-DD). If None, uses today.
            payment_form: SAT payment form code (01=Efectivo, 02=Cheque, 03=Transferencia, 04=Tarjeta, 28=Otros)
        
        Returns:
            Dict with Payment Entry details including exchange gain/loss info
        """
        try:
            si = frappe.get_doc("Sales Invoice", si_name)

            # Intelligent: if SI is Draft, auto-submit it first
            if si.docstatus == 0:
                try:
                    si.submit()
                    frappe.db.commit()
                    si.reload()
                except Exception as submit_err:
                    return {
                        "success": False,
                        "error": f"Sales Invoice '{si_name}' is Draft. Auto-submit failed: {str(submit_err)}"
                    }
            elif si.docstatus == 2:
                return {"success": False, "error": f"Sales Invoice '{si_name}' is cancelled."}

            if flt(si.outstanding_amount) <= 0:
                return {
                    "success": True,
                    "message": f"✅ Sales Invoice {self.make_link('Sales Invoice', si_name)} is already fully paid."
                }

            # Check if Payment Entry already exists for this invoice
            # Query the references child table for this invoice
            existing_pe = frappe.db.sql("""
                SELECT parent FROM `tabPayment Entry Reference`
                WHERE reference_name = %s AND parenttype = 'Payment Entry'
                AND parent IN (SELECT name FROM `tabPayment Entry` WHERE docstatus IN (0, 1))
                LIMIT 1
            """, (si_name,))
            
            if existing_pe and existing_pe[0]:
                existing_pe_name = existing_pe[0][0]
                return {
                    "success": False,
                    "error": f"A Payment Entry already exists for {si_name}: {self.make_link('Payment Entry', existing_pe_name)}\n\n"
                              f"Use: `@ai payment submit {existing_pe_name}` to submit it, or check outstanding with `@ai payment status {existing_pe_name}`"
                }

            payment_amount = flt(amount) if amount else flt(si.outstanding_amount)

            if payment_amount > flt(si.outstanding_amount):
                return {
                    "success": False,
                    "error": (
                        f"Payment amount ({payment_amount}) exceeds outstanding "
                        f"({si.outstanding_amount}) on {si_name}."
                    )
                }

            # Use ERPNext's built-in Payment Entry creation
            # Try make_payment_entry first (more robust), fallback to get_payment_entry
            try:
                from erpnext.accounts.doctype.payment_entry.payment_entry import make_payment_entry
                pe = make_payment_entry(si_name)
                if pe:
                    # make_payment_entry returns the PE doc, configure it
                    if payment_amount and payment_amount != si.outstanding_amount:
                        # Adjust amount if partial payment
                        for ref in pe.references:
                            ref.allocated_amount = payment_amount
                            ref.outstanding_amount = si.outstanding_amount - payment_amount
                        pe.paid_amount = payment_amount
                        pe.total_allocated = payment_amount
            except Exception as make_err:
                # Fallback to get_payment_entry
                from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
                pe = get_payment_entry("Sales Invoice", si_name, party_amount=payment_amount)

            # Set mode_of_payment - default to Wire Transfer if not provided
            if mode_of_payment:
                pe.mode_of_payment = mode_of_payment
            elif not pe.mode_of_payment:
                # Try to get from customer defaults, otherwise use Wire Transfer
                default_mop = frappe.db.get_value("Customer", si.customer, "default_mode_of_payment")
                pe.mode_of_payment = default_mop or "Wire Transfer"

            pe.reference_no = f"PAY-{si_name}"
            pe.reference_date = payment_date or nowdate()
            if payment_date:
                pe.posting_date = payment_date

            # Ensure required fields are set - comprehensive fix
            # For Receive Payment (from customer), we need:
            # - paid_from: Bank/Cash account (where money goes INTO)
            # - paid_to: Receivable account ( customer's debt to us)
            
            # Get the customer's receivable account
            if not pe.paid_from:
                # This should be set by get_payment_entry but ensure it
                party_account = frappe.db.get_value("Party Account", 
                    {"parent": si.customer, "parenttype": "Customer", "company": si.company},
                    "account")
                if party_account:
                    pe.paid_from = party_account
                else:
                    # Fallback to company default receivable
                    pe.paid_from = frappe.db.get_value("Company", si.company, "default_receivable_account")
            
            #paid_to should be our bank/cash account
            if not pe.paid_to:
                # Get default cash or bank account from company
                cash_account = frappe.db.get_value("Company", si.company, "default_cash_account")
                bank_account = frappe.db.get_value("Company", si.company, "default_bank_account")
                pe.paid_to = cash_account or bank_account or "Cash - AMB-W"
            
            # Ensure we have a valid mode of payment with proper account
            if not pe.mode_of_payment:
                pe.mode_of_payment = "Wire Transfer"
            
            # If mode_of_payment is set, ensure we have the payment account from MOP
            if pe.mode_of_payment:
                mop_account = frappe.db.get_value("Mode of Payment Account", 
                    {"parent": pe.mode_of_payment, "company": si.company},
                    "default_account")
                if mop_account and not pe.paid_to:
                    pe.paid_to = mop_account
            
            # CRITICAL: Set payment_form - SAT Mexico requirement (custom field)
            # Valid codes: 01=Efectivo, 02=Cheque, 03=Transferencia, 04=Tarjeta, 28=Otros
            # Use parameter if provided, otherwise infer from mode_of_payment
            if payment_form:
                pe.payment_form = payment_form
            elif not getattr(pe, 'payment_form', None):
                mop_lower = (pe.mode_of_payment or "").lower()
                if "transfer" in mop_lower:
                    pe.payment_form = "03"  # Transferencia
                elif "cash" in mop_lower or "efectivo" in mop_lower:
                    pe.payment_form = "01"  # Efectivo
                elif "cheque" in mop_lower:
                    pe.payment_form = "02"  # Cheque
                elif "tarjeta" in mop_lower or "card" in mop_lower:
                    pe.payment_form = "04"  # Tarjeta
                else:
                    pe.payment_form = "01"  # Default to Efectivo

            # --- Banxico FIX T-1 Exchange Rate for Payment Date ---
            fx_info = None
            exchange_gl_info = None
            company_currency = frappe.db.get_value('Company', si.company, 'default_currency') or 'MXN'
            
            if si.currency != company_currency:
                posting = str(pe.posting_date or nowdate())
                try:
                    from raven_ai_agent.api.banxico_fx import (
                        get_fix_for_payment, calculate_exchange_gain_loss
                    )
                    payment_rate, rate_date = get_fix_for_payment(posting)
                    if payment_rate:
                        # Set the payment exchange rate
                        pe.source_exchange_rate = payment_rate
                        pe.target_exchange_rate = 1  # MXN -> MXN
                        
                        fx_info = {
                            'payment_rate': payment_rate,
                            'rate_date': rate_date,
                            'invoice_rate': si.conversion_rate
                        }
                        
                        # Calculate exchange gain/loss
                        # For receive payment: paid_amount is in USD
                        usd_amount = flt(payment_amount) if si.party_account_currency == 'MXN' else flt(pe.paid_amount)
                        if si.party_account_currency == 'MXN':
                            # outstanding is in MXN, payment is in USD
                            # Need the USD amount being paid
                            usd_amount = flt(pe.paid_amount) if hasattr(pe, 'paid_amount') else payment_amount
                        
                        exchange_gl_info = calculate_exchange_gain_loss(
                            invoice_rate=si.conversion_rate,
                            payment_rate=payment_rate,
                            usd_amount=usd_amount
                        )
                        
                        # ERPNext handles exchange gain/loss automatically via
                        # "Set Exchange Gain/Loss" when source_exchange_rate differs
                        # from the invoice conversion_rate. The difference posts to
                        # the company's exchange_gain_loss_account.
                        
                except Exception:
                    pass  # Banxico not available, let ERPNext use its default rate

            pe.insert(ignore_permissions=True)
            frappe.db.commit()

            # Get company currency for the payment (outstanding_amount is in company currency)
            company_currency = frappe.db.get_value("Company", si.company, "default_currency") or "MXN"
            
            # Build response message
            fx_msg = ""
            if fx_info:
                fx_msg = (
                    f"\n\n  💱 **Tipo de Cambio**\n"
                    f"  Invoice TC: {fx_info['invoice_rate']} (at invoice date)\n"
                    f"  Payment TC: {fx_info['payment_rate']} (FIX {fx_info['rate_date']})\n"
                )
                if exchange_gl_info and exchange_gl_info['difference_mxn'] > 0.01:
                    gl_type = '🟢 Ganancia' if exchange_gl_info['is_gain'] else '🔴 Pérdida'
                    fx_msg += (
                        f"  {gl_type} cambiaria: MXN {exchange_gl_info['difference_mxn']:,.2f}\n"
                        f"  ({exchange_gl_info['type_es']})"
                    )

            return {
                "success": True,
                "pe_name": pe.name,
                "link": self.make_link("Payment Entry", pe.name),
                "fx_info": fx_info,
                "exchange_gain_loss": exchange_gl_info,
                "message": (
                    f"✅ Payment Entry created: {self.make_link('Payment Entry', pe.name)}\n\n"
                    f"  Sales Invoice: {self.make_link('Sales Invoice', si_name)}\n"
                    f"  Customer: {si.customer}\n"
                    f"  Amount: {payment_amount} {company_currency}\n"
                    f"  Outstanding After: {flt(si.outstanding_amount) - payment_amount} {company_currency}\n"
                    f"  Status: Draft"
                    f"{fx_msg}\n\n"
                    f"💡 Review and submit: `@ai payment submit {pe.name}`"
                )
            }

        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Sales Invoice '{si_name}' not found."}
        except Exception as e:
            import traceback
            error_detail = str(e)
            # Try to get more details from the validation error
            if hasattr(frappe, 'local') and hasattr(frappe.local, 'form_dict'):
                error_detail += f" | Form: {frappe.local.form_dict.get('form_name', 'unknown')}"
            return {
                "success": False, 
                "error": f"Error creating Payment Entry: {error_detail}",
                "traceback": traceback.format_exc()
            }

    def submit_payment_entry(self, pe_name: str) -> Dict:
        """Submit a Payment Entry.
        
        Args:
            pe_name: Payment Entry name
        
        Returns:
            Dict with submission status
        """
        try:
            pe = frappe.get_doc("Payment Entry", pe_name)

            if pe.docstatus == 1:
                return {
                    "success": True,
                    "message": f"✅ Payment Entry {self.make_link('Payment Entry', pe_name)} is already submitted."
                }
            if pe.docstatus == 2:
                return {"success": False, "error": f"Payment Entry {pe_name} is cancelled."}

            # Pre-flight check: Ensure Customer has primary address and contact
            # This prevents "Please, update Customer Primary Address" errors
            preflight = self._ensure_customer_address_and_contact(pe)
            if not preflight["success"]:
                # Return helpful error with manual action link
                return {"success": False, "error": preflight["error"]}
            
            # If we fixed something, reload the PE to get updated references
            if preflight["fixed"]:
                frappe.db.commit()
                pe.reload()

            pe.submit()
            frappe.db.commit()

            # Build success message with any fixes applied
            fix_msg = ""
            if preflight["fixed"]:
                fix_msg = f"\n\n🔧 **Auto-fixed:** {', '.join(preflight['fixed'])}"

            return {
                "success": True,
                "pe_name": pe.name,
                "link": self.make_link("Payment Entry", pe.name),
                "message": (
                    f"✅ Payment Entry submitted: {self.make_link('Payment Entry', pe.name)}\n\n"
                    f"  Party: {pe.party_name}\n"
                    f"  Amount: {pe.paid_amount} {pe.paid_from_account_currency}\n"
                    f"  Mode: {pe.mode_of_payment or 'Not set'}\n"
                    f"  Reference: {pe.reference_no or 'N/A'}"
                    f"{fix_msg}"
                )
            }

        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Payment Entry '{pe_name}' not found."}
        except Exception as e:
            error_msg = str(e)
            error_lower = error_msg.lower()
            
            # BUG 89B FIX: Check for encryption key mismatch errors
            if "unauthorized" in error_lower or "encryption key" in error_lower or "decrypt" in error_lower:
                return {
                    "success": False, 
                    "error": (
                        "❌ Cannot submit Payment Entry: Site encryption key mismatch detected.\n\n"
                        "The site was recently restored from a backup and the encryption key in site_config.json "
                        "doesn't match the original key used to encrypt sensitive fields.\n\n"
                        "🔧 **Solution:** Ask your system administrator to restore the original encryption_key "
                        "from the source site's site_config.json into the current site's site_config.json.\n\n"
                        "This is an infrastructure issue, not a code problem."
                    )
                }
            
            # Check for Customer tax_system validation errors (Mexican CFDI requirement)
            if "tax_system" in error_lower and "must be" in error_lower:
                # Extract the required tax system value
                import re
                match = re.search(r'must be \[(\d+)\]', error_msg)
                required_tax_system = match.group(1) if match else "616"
                
                # Get the customer name from the PE
                customer_name = ""
                try:
                    pe = frappe.get_doc("Payment Entry", pe_name)
                    customer_name = pe.party or ""
                except:
                    pass
                
                # Auto-fix: Try to update the customer's tax_system
                if customer_name:
                    try:
                        customer = frappe.get_doc("Customer", customer_name)
                        old_tax_system = customer.tax_system or "not set"
                        customer.tax_system = required_tax_system
                        customer.save()
                        frappe.db.commit()
                        
                        # Retry the payment entry submission
                        pe.reload()
                        pe.submit()
                        frappe.db.commit()
                        
                        return {
                            "success": True,
                            "pe_name": pe.name,
                            "link": self.make_link("Payment Entry", pe.name),
                            "message": (
                                f"✅ Payment Entry submitted: {self.make_link('Payment Entry', pe.name)}\n\n"
                                f"  Party: {pe.party_name}\n"
                                f"  Amount: {pe.paid_amount} {pe.paid_from_account_currency}\n\n"
                                f"🔧 **Auto-fixed:** Updated Customer **{customer_name}** tax_system from **{old_tax_system}** to **{required_tax_system}** for CFDI compliance."
                            )
                        }
                    except Exception as auto_fix_error:
                        # If auto-fix fails, fall back to manual instructions
                        frappe.db.rollback()
                        return {
                            "success": False,
                            "error": (
                                f"❌ Cannot submit Payment Entry: Customer tax_system validation failed.\n\n"
                                f"The Customer **{customer_name}** must have tax_system set to **{required_tax_system}** "
                                f"for Mexican CFDI compliance.\n\n"
                                f"🔧 **Solution:** \n"
                                f"1. Go to the Customer form: [{customer_name}](https://{frappe.local.site}/app/customer/{customer_name})\n"
                                f"2. Update the **Tax Regime** (tax_system) field to the correct SAT code\n"
                                f"3. Common valid codes: 601 (General), 605 (S.A. de C.V.), 606 (S. de R.L.), 616 (R.F.B.)\n\n"
                                f"This is a CFDI/Mexican tax compliance requirement.\n\n"
                                f"Auto-fix attempted but failed: {str(auto_fix_error)}"
                            )
                        }
                
                # No customer name found - return manual instructions
                return {
                    "success": False,
                    "error": (
                        f"❌ Cannot submit Payment Entry: Customer tax_system validation failed.\n\n"
                        f"The Customer **{customer_name}** must have tax_system set to **{required_tax_system}** "
                        f"for Mexican CFDI compliance.\n\n"
                        f"🔧 **Solution:** \n"
                        f"1. Go to the Customer form: [{customer_name}](https://{frappe.local.site}/app/customer/{customer_name})\n"
                        f"2. Update the **Tax Regime** (tax_system) field to the correct SAT code\n"
                        f"3. Common valid codes: 601 (General), 605 (S.A. de C.V.), 606 (S. de R.L.), 616 (R.F.B.)\n\n"
                        f"This is a CFDI/Mexican tax compliance requirement."
                    )
                }
            
            return {"success": False, "error": f"Error submitting Payment Entry: {error_msg}"}

    def reconcile_payment(self, pe_name: str) -> Dict:
        """Check reconciliation status of a Payment Entry against its Sales Invoice(s).
        
        Args:
            pe_name: Payment Entry name
        
        Returns:
            Dict with reconciliation details
        """
        try:
            pe = frappe.get_doc("Payment Entry", pe_name)

            if pe.docstatus != 1:
                return {"success": False, "error": f"Payment Entry '{pe_name}' must be submitted first."}

            references = []
            for ref in pe.references:
                if ref.reference_doctype == "Sales Invoice":
                    si = frappe.get_doc("Sales Invoice", ref.reference_name)
                    references.append({
                        "invoice": ref.reference_name,
                        "invoice_link": self.make_link("Sales Invoice", ref.reference_name),
                        "allocated_amount": ref.allocated_amount,
                        "outstanding": si.outstanding_amount,
                        "fully_paid": flt(si.outstanding_amount) <= 0
                    })

            all_reconciled = all(r["fully_paid"] for r in references) if references else False

            msg = f"🔄 **Reconciliation for {self.make_link('Payment Entry', pe_name)}**\n\n"
            msg += f"  Paid Amount: {pe.paid_amount} {pe.paid_from_account_currency}\n"
            msg += f"  Party: {pe.party_name}\n\n"

            if references:
                msg += "| Invoice | Allocated | Outstanding | Status |\n"
                msg += "|---------|-----------|-------------|--------|\n"
                for ref in references:
                    status = "✅ Paid" if ref["fully_paid"] else f"⏳ {ref['outstanding']} remaining"
                    msg += (
                        f"| {ref['invoice_link']} | {ref['allocated_amount']} | "
                        f"{ref['outstanding']} | {status} |\n"
                    )
            else:
                msg += "⚠️ No invoice references found on this Payment Entry.\n"

            msg += f"\n{'✅ Fully reconciled' if all_reconciled else '⏳ Partially reconciled or unreconciled'}"

            return {
                "success": True,
                "reconciled": all_reconciled,
                "references": references,
                "message": msg
            }

        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Payment Entry '{pe_name}' not found."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ========== STATUS & TRACKING ==========

    def get_outstanding_invoices(self, customer: str = None, limit: int = 20) -> Dict:
        """Get list of outstanding (unpaid) Sales Invoices.
        
        Args:
            customer: Filter by customer name. If None, shows all.
            limit: Max results to return.
        
        Returns:
            Dict with outstanding invoices
        """
        try:
            filters = {
                "docstatus": 1,
                "outstanding_amount": [">", 0]
            }
            if customer:
                filters["customer"] = customer

            invoices = frappe.get_all("Sales Invoice",
                filters=filters,
                fields=["name", "customer", "grand_total", "outstanding_amount",
                         "currency", "posting_date", "due_date"],
                order_by="due_date asc",
                limit=limit)

            if not invoices:
                msg = "✅ No outstanding invoices found."
                if customer:
                    msg += f" (Customer: {customer})"
                return {"success": True, "count": 0, "message": msg}

            total_outstanding = sum(flt(inv.outstanding_amount) for inv in invoices)

            msg = f"💰 **Outstanding Invoices** ({len(invoices)} found)\n\n"
            msg += "| Invoice | Customer | Total | Outstanding | Currency | Due Date |\n"
            msg += "|---------|----------|-------|-------------|----------|----------|\n"
            for inv in invoices:
                msg += (
                    f"| {self.make_link('Sales Invoice', inv.name)} | "
                    f"{inv.customer} | {inv.grand_total} | "
                    f"{inv.outstanding_amount} | {inv.currency} | {inv.due_date} |\n"
                )
            msg += f"\n**Total Outstanding: {total_outstanding}**"

            return {
                "success": True,
                "count": len(invoices),
                "total_outstanding": total_outstanding,
                "invoices": invoices,
                "message": msg
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_payment_status(self, pe_name: str) -> Dict:
        """Get detailed status of a Payment Entry."""
        try:
            pe = frappe.get_doc("Payment Entry", pe_name)

            status_text = "Draft" if pe.docstatus == 0 else ("Submitted" if pe.docstatus == 1 else "Cancelled")

            msg = (
                f"💳 **Payment Entry {self.make_link('Payment Entry', pe.name)}**\n\n"
                f"  Party: {pe.party_name}\n"
                f"  Paid Amount: {pe.paid_amount} {pe.paid_from_account_currency}\n"
                f"  Mode: {pe.mode_of_payment or 'Not set'}\n"
                f"  Reference: {pe.reference_no or 'N/A'}\n"
                f"  Date: {pe.reference_date or pe.posting_date}\n"
                f"  Status: **{status_text}**\n\n"
                f"  ➡️ Next: {self.PAYMENT_STATUS_MAP.get(status_text, 'Review manually')}"
            )

            return {
                "success": True,
                "pe_name": pe.name,
                "link": self.make_link("Payment Entry", pe.name),
                "status": status_text,
                "message": msg
            }

        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Payment Entry '{pe_name}' not found."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ========== MAIN COMMAND HANDLER ==========

    def process_command(self, message: str) -> str:
        """Process incoming Raven command and return formatted response.
        
        Commands:
            @ai payment create [SI-NAME]
            @ai payment create [SI-NAME] amount [AMOUNT]
            @ai payment submit [PE-NAME]
            @ai payment reconcile [PE-NAME]
            @ai payment outstanding [CUSTOMER]
            @ai payment status [PE-NAME]
            @ai payment help
        """
        message_lower = message.lower().strip()

        # Extract document names - Updated to match ACC-SINV-2026-00001 format
        si_pattern = r'(ACC-SINV-\d+-\d+|SINV-\d+|SI-[\w-]+|SAL-INV-[\d-]+)'
        si_match = re.search(si_pattern, message, re.IGNORECASE)
        si_name = si_match.group(1) if si_match else None

        pe_pattern = r'(ACC-PAY-\d+-\d+|PE-[\w-]+|PAY-[\w-]+)'
        pe_match = re.search(pe_pattern, message, re.IGNORECASE)
        pe_name = pe_match.group(1) if pe_match else None

        # ---- HELP ----
        if "help" in message_lower or "capabilities" in message_lower:
            return self._help_text()

        # ---- CREATE PAYMENT ----
        # Match: explicit "create" OR just having an SI name (default action for SI = create payment)
        # Also matches: "payment from ACC-SINV-XXX", "pay ACC-SINV-XXX", "pago ACC-SINV-XXX"
        # Handle "create payment for ACC-SINV-XXX" pattern
        if "for" in message_lower and si_name:
            # Extract SI from "create payment for ACC-SINV-XXX"
            for_match = re.search(r'for\s+(ACC-SINV-\d+-\d+|SINV-\d+)', message, re.IGNORECASE)
            if for_match:
                si_name = for_match.group(1)
        
        if si_name and not any(kw in message_lower for kw in ["submit", "reconcile", "status", "estado"]):
            amount_match = re.search(r'(?:amount|monto)\s+(\d+\.?\d*)', message, re.IGNORECASE)
            amount = float(amount_match.group(1)) if amount_match else None
            mode_match = re.search(r'(?:mode|modo)\s+(.+?)(?:\s|$)', message, re.IGNORECASE)
            mode = mode_match.group(1).strip() if mode_match else None
            # Parse payment_form (SAT code: 01, 02, 03, 04, 28)
            form_match = re.search(r'(?:form|forma)\s+(\d+)', message, re.IGNORECASE)
            payment_form = form_match.group(1) if form_match else None
            result = self.create_payment_entry(si_name, amount=amount, mode_of_payment=mode, payment_form=payment_form)
            return result.get("message", result.get("error", "Unknown error"))

        # ---- SUBMIT PAYMENT ----
        if "submit" in message_lower and pe_name:
            result = self.submit_payment_entry(pe_name)
            return result.get("message", result.get("error", "Unknown error"))

        # ---- RECONCILE ----
        if "reconcile" in message_lower and pe_name:
            result = self.reconcile_payment(pe_name)
            return result.get("message", result.get("error", "Unknown error"))

        # ---- OUTSTANDING INVOICES ----
        if "outstanding" in message_lower or "unpaid" in message_lower or "pendiente" in message_lower:
            # Extract customer name if present
            customer_match = re.search(r'(?:customer|cliente|for)\s+(.+)', message, re.IGNORECASE)
            customer = customer_match.group(1).strip() if customer_match else None
            result = self.get_outstanding_invoices(customer=customer)
            return result.get("message", result.get("error", "Unknown error"))

        # ---- PAYMENT STATUS ----
        if ("status" in message_lower or "estado" in message_lower) and pe_name:
            result = self.get_payment_status(pe_name)
            return result.get("message", result.get("error", "Unknown error"))

        # ---- FALLBACK ----
        return self._help_text()

    def _help_text(self) -> str:
        return (
            "💳 **Payment Agent — Commands**\n\n"
            "**Payment Creation**\n"
            "`@ai payment create [SI-NAME]` — Create Payment Entry from Sales Invoice\n"
            "`@ai payment create [SI-NAME] amount [AMOUNT]` — Partial payment\n\n"
            "**Payment Actions**\n"
            "`@ai payment submit [PE-NAME]` — Submit Payment Entry\n"
            "`@ai payment reconcile [PE-NAME]` — Check reconciliation status\n\n"
            "**Status & Tracking**\n"
            "`@ai payment outstanding` — List all unpaid invoices\n"
            "`@ai payment outstanding customer [NAME]` — Unpaid invoices for customer\n"
            "`@ai payment status [PE-NAME]` — Payment Entry details\n\n"
            "**Example (Full Cycle)**\n"
            "```\n"
            "@ai payment create ACC-SINV-2026-00001\n"
            "@ai payment submit ACC-PAY-2026-00001\n"
            "@ai payment reconcile ACC-PAY-2026-00001\n"
            "```"
        )
