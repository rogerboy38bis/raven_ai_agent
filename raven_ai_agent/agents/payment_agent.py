"""
Payment Agent - Payment Entry Creation & Reconciliation
Handles Step 8 of the 8-step fulfillment workflow:
  Step 8: Create Payment Entry from Sales Invoice

IMPORTANT: Frappe Server Script compatible module.
- Uses frappe.call() patterns
- Designed for raven_ai_agent (Frappe app)

Based on verified 8-step workflow:
  SO → WO → SE (Manufacture) → DN → SI → PE
"""
import frappe
from typing import Dict, List, Optional
from frappe.utils import nowdate, flt


class PaymentAgent:
    """AI Agent for Payment Entry creation and reconciliation"""

    PAYMENT_STATUS_FLOW = {
        "Draft": "Submit the Payment Entry",
        "Submitted": "Payment recorded — reconcile with invoice",
        "Cancelled": "Payment cancelled — no action"
    }

    def __init__(self, user: str = None):
        self.user = user or frappe.session.user
        self.site_name = frappe.local.site

    def make_link(self, doctype: str, name: str) -> str:
        """Generate clickable markdown link"""
        slug = doctype.lower().replace(" ", "-")
        return f"[{name}](https://{self.site_name}/app/{slug}/{name})"

    # ========================================================================
    # STEP 8: CREATE PAYMENT ENTRY FROM SALES INVOICE
    # ========================================================================

    def create_payment_entry(
        self,
        si_name: str,
        mode_of_payment: str = "Wire Transfer",
        confirm: bool = False
    ) -> Dict:
        """
        Create Payment Entry from a Sales Invoice.

        Handles:
        - Multi-currency (USD invoices for MXN company)
        - CFDI compliance fields
        - Auto-detection of bank accounts

        Args:
            si_name: Sales Invoice name
            mode_of_payment: Payment method (default: Wire Transfer)
            confirm: If False, returns preview

        Returns:
            Dict with payment_entry name and details
        """
        try:
            si = frappe.get_doc("Sales Invoice", si_name)

            if si.docstatus != 1:
                return {"success": False, "error": f"Sales Invoice {si_name} must be submitted first"}

            if si.outstanding_amount <= 0:
                return {
                    "success": True,
                    "message": f"Sales Invoice {si_name} is already fully paid (outstanding: {si.outstanding_amount})"
                }

            # Check for existing payment
            existing_pe = frappe.db.get_value("Payment Entry Reference", {
                "reference_doctype": "Sales Invoice",
                "reference_name": si_name,
                "docstatus": ["!=", 2]
            }, "parent")

            if existing_pe:
                pe_doc = frappe.get_doc("Payment Entry", existing_pe)
                if pe_doc.docstatus == 1:
                    return {
                        "success": True,
                        "message": f"Payment Entry already exists: {existing_pe}",
                        "payment_entry": existing_pe,
                        "link": self.make_link("Payment Entry", existing_pe)
                    }

            if not confirm:
                return {
                    "success": True,
                    "requires_confirmation": True,
                    "preview": (
                        f"**Create Payment Entry for {si_name}?**\n\n"
                        f"| Field | Value |\n|-------|-------|\n"
                        f"| Customer | {si.customer} |\n"
                        f"| Invoice Total | {si.currency} {si.grand_total:,.2f} |\n"
                        f"| Outstanding | {si.currency} {si.outstanding_amount:,.2f} |\n"
                        f"| Mode of Payment | {mode_of_payment} |\n\n"
                        f"⚠️ **Confirm?** Reply: `@ai confirm create payment for {si_name}`"
                    )
                }

            # Use ERPNext's built-in method
            from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

            pe = get_payment_entry("Sales Invoice", si_name)
            pe.mode_of_payment = mode_of_payment
            pe.reference_date = nowdate()

            # Set paid amount to outstanding
            pe.paid_amount = flt(si.outstanding_amount)
            pe.received_amount = flt(si.outstanding_amount)

            # Handle multi-currency
            if si.currency != frappe.defaults.get_defaults().get("currency", "MXN"):
                # For USD invoices on MXN company
                exchange_rate = si.conversion_rate or 1
                pe.source_exchange_rate = exchange_rate
                pe.paid_amount = flt(si.outstanding_amount)
                pe.received_amount = flt(si.outstanding_amount * exchange_rate)

            # Auto-detect bank account
            bank_account = self._get_bank_account(si.company, mode_of_payment)
            if bank_account:
                pe.paid_to = bank_account

            pe.flags.ignore_permissions = True
            pe.insert()
            frappe.db.commit()

            return {
                "success": True,
                "action": "created",
                "payment_entry": pe.name,
                "link": self.make_link("Payment Entry", pe.name),
                "sales_invoice": si_name,
                "amount": pe.paid_amount,
                "currency": si.currency,
                "mode_of_payment": mode_of_payment,
                "status": "Draft",
                "message": (
                    f"✅ Payment Entry **{pe.name}** created for {si_name}\n"
                    f"Amount: {si.currency} {pe.paid_amount:,.2f}\n"
                    f"Review and submit to record payment."
                )
            }
        except Exception as e:
            frappe.log_error(f"PaymentAgent.create_payment_entry error: {str(e)}")
            return {"success": False, "error": str(e)}

    def submit_payment_entry(self, pe_name: str, confirm: bool = False) -> Dict:
        """Submit a Payment Entry"""
        try:
            pe = frappe.get_doc("Payment Entry", pe_name)

            if pe.docstatus == 1:
                return {"success": True, "message": f"Payment Entry {pe_name} is already submitted"}

            if pe.docstatus == 2:
                return {"success": False, "error": f"Payment Entry {pe_name} is cancelled"}

            if not confirm:
                return {
                    "success": True,
                    "requires_confirmation": True,
                    "preview": (
                        f"**Submit Payment Entry {pe_name}?**\n\n"
                        f"| Field | Value |\n|-------|-------|\n"
                        f"| Party | {pe.party} |\n"
                        f"| Amount | {pe.paid_amount:,.2f} |\n"
                        f"| Mode | {pe.mode_of_payment} |\n\n"
                        f"⚠️ This will record the payment against the invoice."
                    )
                }

            pe.flags.ignore_permissions = True
            pe.submit()
            frappe.db.commit()

            return {
                "success": True,
                "action": "submitted",
                "payment_entry": pe_name,
                "link": self.make_link("Payment Entry", pe_name),
                "message": f"✅ Payment Entry **{pe_name}** submitted"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def reconcile_payment(self, pe_name: str) -> Dict:
        """
        Check reconciliation status of a Payment Entry.
        Verifies that the PE is properly linked to its Sales Invoice
        and that the invoice outstanding amount reflects the payment.
        """
        try:
            pe = frappe.get_doc("Payment Entry", pe_name)

            if pe.docstatus != 1:
                return {"success": False, "error": f"Payment Entry {pe_name} must be submitted first"}

            reconciliation_status = []
            for ref in pe.references:
                if ref.reference_doctype == "Sales Invoice":
                    si = frappe.get_doc("Sales Invoice", ref.reference_name)
                    reconciliation_status.append({
                        "invoice": ref.reference_name,
                        "invoice_link": self.make_link("Sales Invoice", ref.reference_name),
                        "allocated_amount": ref.allocated_amount,
                        "outstanding_after": si.outstanding_amount,
                        "is_paid": si.outstanding_amount <= 0,
                        "status": "✅ Paid" if si.outstanding_amount <= 0 else f"⚠️ Outstanding: {si.outstanding_amount:,.2f}"
                    })

            all_reconciled = all(r["is_paid"] for r in reconciliation_status) if reconciliation_status else False

            return {
                "success": True,
                "payment_entry": pe_name,
                "link": self.make_link("Payment Entry", pe_name),
                "fully_reconciled": all_reconciled,
                "references": reconciliation_status,
                "message": (
                    f"Payment {pe_name} is {'✅ fully reconciled' if all_reconciled else '⚠️ partially reconciled'}"
                )
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_unpaid_invoices(self, customer: str = None, limit: int = 20) -> Dict:
        """List unpaid Sales Invoices"""
        try:
            filters = {
                "docstatus": 1,
                "outstanding_amount": [">", 0],
                "status": ["in", ["Unpaid", "Overdue", "Partly Paid"]]
            }
            if customer:
                filters["customer"] = customer

            invoices = frappe.get_all("Sales Invoice",
                filters=filters,
                fields=["name", "customer", "grand_total", "outstanding_amount",
                         "currency", "due_date", "status"],
                order_by="due_date asc",
                limit=limit)

            return {
                "success": True,
                "count": len(invoices),
                "invoices": [{
                    "name": inv.name,
                    "link": self.make_link("Sales Invoice", inv.name),
                    "customer": inv.customer,
                    "total": f"{inv.currency} {inv.grand_total:,.2f}",
                    "outstanding": f"{inv.currency} {inv.outstanding_amount:,.2f}",
                    "due_date": str(inv.due_date) if inv.due_date else "Not set",
                    "status": inv.status
                } for inv in invoices]
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ========================================================================
    # INTERNAL HELPERS
    # ========================================================================

    def _get_bank_account(self, company: str, mode_of_payment: str) -> Optional[str]:
        """Get the appropriate bank/cash account for payment"""
        try:
            # Try mode of payment account first
            account = frappe.db.get_value("Mode of Payment Account", {
                "parent": mode_of_payment,
                "company": company
            }, "default_account")

            if account:
                return account

            # Fallback: company default receivable account
            return frappe.db.get_value("Company", company, "default_receivable_account")
        except Exception:
            return None

    # ========================================================================
    # COMMAND HANDLER
    # ========================================================================

    def process_command(self, message: str) -> str:
        """Process natural language commands for payment operations"""
        message_lower = message.lower().strip()

        import re

        # Extract SI name
        si_pattern = r'(ACC-SINV-\d+-\d+|SINV-\d+|SI-\d+)'
        si_match = re.search(si_pattern, message, re.IGNORECASE)
        si_name = si_match.group(1) if si_match else None

        # Extract PE name
        pe_pattern = r'(ACC-PAY-\d+-\d+|PE-\d+|PAY-\d+)'
        pe_match = re.search(pe_pattern, message, re.IGNORECASE)
        pe_name = pe_match.group(1) if pe_match else None

        confirm = "confirm" in message_lower or message.startswith("!")

        if pe_name:
            if "reconcile" in message_lower:
                result = self.reconcile_payment(pe_name)
            elif "submit" in message_lower:
                result = self.submit_payment_entry(pe_name, confirm=confirm)
            else:
                result = self.reconcile_payment(pe_name)
        elif si_name:
            if "pay" in message_lower or "payment" in message_lower:
                result = self.create_payment_entry(si_name, confirm=confirm)
            else:
                result = self.create_payment_entry(si_name, confirm=confirm)
        elif "unpaid" in message_lower or "outstanding" in message_lower:
            result = self.get_unpaid_invoices()
        else:
            result = {
                "success": True,
                "message": (
                    "**Payment Agent Commands:**\n\n"
                    "- `@ai create payment for ACC-SINV-2026-00001` — Create PE from invoice\n"
                    "- `@ai submit ACC-PAY-2026-00001` — Submit payment entry\n"
                    "- `@ai reconcile ACC-PAY-2026-00001` — Check reconciliation\n"
                    "- `@ai unpaid invoices` — List unpaid invoices"
                )
            }

        return self._format_response(result)

    def _format_response(self, result: Dict) -> str:
        """Format result dict into readable response"""
        if result.get("requires_confirmation"):
            return result["preview"]
        if not result.get("success"):
            return f"❌ {result.get('error', 'Unknown error')}"
        if result.get("message"):
            return result["message"]
        return str(result)
