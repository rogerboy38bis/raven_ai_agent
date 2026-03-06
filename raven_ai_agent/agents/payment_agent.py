"""
Payment AI Agent
Handles Payment Entry creation and reconciliation from Sales Invoices.

Covers Workflow Step 8:
  Step 8: Payment Entry from Sales Invoice

Key Intelligence:
  - Creates Payment Entry from submitted Sales Invoice
  - Handles multi-currency (USD sales with MXN company)
  - Reconciles Payment Entry with Sales Invoice
  - Tracks outstanding amounts
  - CFDI compliance awareness

Author: raven_ai_agent
"""
import frappe
import re
from typing import Dict, List, Optional
from frappe.utils import nowdate, getdate, flt


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

    # ========== PAYMENT ENTRY OPERATIONS (Step 8) ==========

    def create_payment_entry(self, si_name: str, amount: float = None,
                             mode_of_payment: str = None) -> Dict:
        """Create a Payment Entry from a Sales Invoice.
        
        Args:
            si_name: Sales Invoice name
            amount: Payment amount. If None, uses full outstanding amount.
            mode_of_payment: Mode of payment (e.g. 'Wire Transfer', 'Cash')
        
        Returns:
            Dict with Payment Entry details
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
            from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

            pe = get_payment_entry("Sales Invoice", si_name, party_amount=payment_amount)

            if mode_of_payment:
                pe.mode_of_payment = mode_of_payment

            pe.reference_no = f"PAY-{si_name}"
            pe.reference_date = nowdate()

            pe.insert(ignore_permissions=True)
            frappe.db.commit()

            return {
                "success": True,
                "pe_name": pe.name,
                "link": self.make_link("Payment Entry", pe.name),
                "message": (
                    f"✅ Payment Entry created: {self.make_link('Payment Entry', pe.name)}\n\n"
                    f"  Sales Invoice: {self.make_link('Sales Invoice', si_name)}\n"
                    f"  Customer: {si.customer}\n"
                    f"  Amount: {payment_amount} {si.currency}\n"
                    f"  Outstanding After: {flt(si.outstanding_amount) - payment_amount}\n"
                    f"  Status: Draft\n\n"
                    f"💡 Review and submit: `@payment submit {pe.name}`"
                )
            }

        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Sales Invoice '{si_name}' not found."}
        except Exception as e:
            return {"success": False, "error": f"Error creating Payment Entry: {str(e)}"}

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

            pe.submit()
            frappe.db.commit()

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
                )
            }

        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Payment Entry '{pe_name}' not found."}
        except Exception as e:
            return {"success": False, "error": f"Error submitting Payment Entry: {str(e)}"}

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
            @payment create [SI-NAME]
            @payment create [SI-NAME] amount [AMOUNT]
            @payment submit [PE-NAME]
            @payment reconcile [PE-NAME]
            @payment outstanding [CUSTOMER]
            @payment status [PE-NAME]
            @payment help
        """
        message_lower = message.lower().strip()

        # Extract document names
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
        if si_name and not any(kw in message_lower for kw in ["submit", "reconcile", "status", "estado"]):
            amount_match = re.search(r'(?:amount|monto)\s+(\d+\.?\d*)', message, re.IGNORECASE)
            amount = float(amount_match.group(1)) if amount_match else None
            mode_match = re.search(r'(?:mode|modo)\s+(.+?)(?:\s|$)', message, re.IGNORECASE)
            mode = mode_match.group(1).strip() if mode_match else None
            result = self.create_payment_entry(si_name, amount=amount, mode_of_payment=mode)
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
            "`@payment create [SI-NAME]` — Create Payment Entry from Sales Invoice\n"
            "`@payment create [SI-NAME] amount [AMOUNT]` — Partial payment\n\n"
            "**Payment Actions**\n"
            "`@payment submit [PE-NAME]` — Submit Payment Entry\n"
            "`@payment reconcile [PE-NAME]` — Check reconciliation status\n\n"
            "**Status & Tracking**\n"
            "`@payment outstanding` — List all unpaid invoices\n"
            "`@payment outstanding customer [NAME]` — Unpaid invoices for customer\n"
            "`@payment status [PE-NAME]` — Payment Entry details\n\n"
            "**Example (Full Cycle)**\n"
            "```\n"
            "@payment create ACC-SINV-2026-00001\n"
            "@payment submit ACC-PAY-2026-00001\n"
            "@payment reconcile ACC-PAY-2026-00001\n"
            "```"
        )
