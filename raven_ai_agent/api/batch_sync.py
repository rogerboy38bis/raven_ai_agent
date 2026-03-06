"""
Batch Sync API — Direct endpoint for syncing Sales Orders from Quotations.

NO LLM required. Uses TaskValidatorMixin directly (same pattern as router.py).
Created for batch migration fix of 1,058+ auto-fixable SOs.

Usage:
    POST /api/method/raven_ai_agent.api.batch_sync.batch_sync_so
    Body: {"so_names": ["SO-00744-ALBAFLOR", "SO-00745-XXX", ...]}

    POST /api/method/raven_ai_agent.api.batch_sync.single_sync_so
    Body: {"so_name": "SO-00744-ALBAFLOR", "confirm": true}
"""
import frappe
import json
from typing import Dict, List


@frappe.whitelist()
def single_sync_so(so_name: str, confirm: bool = True) -> Dict:
    """Sync a single SO from its source quotation — no LLM, direct call."""
    from raven_ai_agent.api.handlers.task_validator import TaskValidatorMixin

    class _ValidatorAgent(TaskValidatorMixin):
        pass

    confirm = confirm if isinstance(confirm, bool) else str(confirm).lower() in ("true", "1", "yes")

    validator = _ValidatorAgent()
    result = validator._sync_so_from_quotation(so_name, confirm=confirm)
    return result


@frappe.whitelist()
def batch_sync_so(so_names: str = None) -> Dict:
    """
    Batch sync multiple SOs from their source quotations.
    
    Args:
        so_names: JSON string array of SO names, e.g. '["SO-00744-ALBAFLOR", ...]'
    
    Returns:
        Dict with results per SO: success count, failure count, details.
    """
    from raven_ai_agent.api.handlers.task_validator import TaskValidatorMixin

    if not so_names:
        return {"success": False, "error": "No SO names provided. Pass so_names as JSON array."}

    # Parse JSON string
    if isinstance(so_names, str):
        try:
            so_list = json.loads(so_names)
        except json.JSONDecodeError:
            return {"success": False, "error": "Invalid JSON in so_names parameter."}
    else:
        so_list = so_names

    if not isinstance(so_list, list) or len(so_list) == 0:
        return {"success": False, "error": "so_names must be a non-empty JSON array."}

    class _ValidatorAgent(TaskValidatorMixin):
        pass

    validator = _ValidatorAgent()

    results = {
        "total": len(so_list),
        "success_count": 0,
        "fail_count": 0,
        "skip_count": 0,
        "details": [],
    }

    for idx, so_name in enumerate(so_list):
        so_name = so_name.strip()
        try:
            result = validator._sync_so_from_quotation(so_name, confirm=True)
            is_success = result.get("success", False)
            message = result.get("message", "") or result.get("error", "")

            # Check if "already matches" — that's a skip (no changes needed)
            if is_success and "already matches" in message:
                results["skip_count"] += 1
                results["details"].append({
                    "so": so_name,
                    "status": "skipped",
                    "message": "Already matches quotation",
                })
            elif is_success:
                results["success_count"] += 1
                # Extract change count from message
                change_count = 0
                if "change(s) applied" in message:
                    try:
                        change_count = int(message.split("change(s) applied")[0].split("**")[-1].strip())
                    except (ValueError, IndexError):
                        pass
                results["details"].append({
                    "so": so_name,
                    "status": "synced",
                    "changes": change_count,
                    "message": f"Synced successfully ({change_count} changes)",
                })
            else:
                results["fail_count"] += 1
                results["details"].append({
                    "so": so_name,
                    "status": "failed",
                    "message": message[:200],
                })

        except Exception as e:
            results["fail_count"] += 1
            results["details"].append({
                "so": so_name,
                "status": "error",
                "message": str(e)[:200],
            })

        # Commit every 10 SOs to avoid huge transactions
        if (idx + 1) % 10 == 0:
            frappe.db.commit()

    # Final commit
    frappe.db.commit()

    results["success"] = True
    results["summary"] = (
        f"Batch complete: {results['success_count']} synced, "
        f"{results['skip_count']} already matched, "
        f"{results['fail_count']} failed out of {results['total']}"
    )

    return results
