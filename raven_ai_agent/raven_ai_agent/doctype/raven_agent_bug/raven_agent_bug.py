"""
Raven Agent Bug — central record for an auto-detected agent failure.

Implements the Frappe ``clear_old_logs`` static method so this doctype
shows up automatically in **Log Settings** with configurable retention.
"""
import frappe
from frappe.model.document import Document


class RavenAgentBug(Document):
    @staticmethod
    def clear_old_logs(days: int = 180) -> None:
        """Auto-registered with Log Settings (see Frappe logging docs).

        Deletes Raven Agent Bug records older than ``days`` modified date.
        Default 180 days; user-configurable from Log Settings.
        """
        from frappe.query_builder import Interval
        from frappe.query_builder.functions import Now

        table = frappe.qb.DocType("Raven Agent Bug")
        frappe.db.delete(table, filters=(table.modified < (Now() - Interval(days=days))))


@frappe.whitelist()
def acknowledge(name: str) -> dict:
    """Operator acknowledges a paused bug from the desk UI.

    Sets autonomy_paused=0 and clears alarm flags.  Does NOT delete the
    record (history is valuable).
    """
    bug = frappe.get_doc("Raven Agent Bug", name)
    bug.autonomy_paused = 0
    bug.autonomy_paused_at = None
    bug.alarm1_sent = 0
    bug.alarm2_sent = 0
    bug.alarm3_sent = 0
    bug.save(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True, "name": name}
