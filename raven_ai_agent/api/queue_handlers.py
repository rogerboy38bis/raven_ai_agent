"""
Background Queue Handlers for Raven AI Agent
Phase 2: Optimization

Long-running operations are offloaded to Frappe's background job queue
(Python RQ) to avoid blocking the main request thread.

Usage:
    from raven_ai_agent.api.queue_handlers import enqueue_batch_assignment
    enqueue_batch_assignment(dn_name, channel_id)
"""
import frappe
import json
from typing import Dict, Optional
from frappe.utils import flt, now_datetime


# =============================================================================
# PROGRESS TRACKING
# =============================================================================

def _publish_progress(channel_id: str, task_type: str, progress: int,
                      message: str, task_id: str = None) -> None:
    """Publish progress update to Raven channel and realtime event."""
    # Realtime event for UI progress bars
    frappe.publish_realtime(
        "rai_task_progress",
        {
            "task_type": task_type,
            "task_id": task_id or "",
            "progress": progress,
            "message": message,
            "timestamp": str(now_datetime())
        }
    )


def _send_raven_result(channel_id: str, message: str, bot_name: str = "sales_order_bot") -> None:
    """Send final result message to Raven channel."""
    if not channel_id:
        return
    try:
        from raven_ai_agent.api.channel_utils import publish_message_created_event
        
        # Create Raven message
        msg_doc = frappe.get_doc({
            "doctype": "Raven Message",
            "channel_id": channel_id,
            "text": message,
            "message_type": "Text",
            "bot": bot_name
        })
        msg_doc.insert(ignore_permissions=True)
        frappe.db.commit()
        
        # Publish realtime event
        publish_message_created_event(channel_id, msg_doc.name)
    except Exception as e:
        frappe.log_error(f"Raven message failed: {str(e)}", "RAI Queue Handler")


# =============================================================================
# TASK STATUS TRACKING (persisted in Redis)
# =============================================================================

def set_task_status(task_id: str, status: str, result: Dict = None) -> None:
    """Track async task status in Redis."""
    data = {
        "status": status,  # queued, running, completed, failed
        "updated": str(now_datetime()),
        "result": result or {}
    }
    frappe.cache.set_value(f"rai:task:{task_id}", data, expires_in_sec=3600)


def get_task_status(task_id: str) -> Optional[Dict]:
    """Get async task status from Redis."""
    return frappe.cache.get_value(f"rai:task:{task_id}")


@frappe.whitelist()
def api_task_status(task_id: str) -> str:
    """API endpoint to check task status."""
    status = get_task_status(task_id)
    if status:
        return json.dumps(status)
    return json.dumps({"status": "not_found"})


# =============================================================================
# QUEUED TASK: BATCH AUTO-ASSIGNMENT
# =============================================================================

def enqueue_batch_assignment(dn_name: str, channel_id: str = "") -> Dict:
    """Enqueue batch auto-assignment as a background job.
    
    For DNs with many items (10+ rows with batch requirements),
    this offloads the work to the long queue to avoid request timeout.
    
    Returns task_id for status tracking.
    """
    task_id = f"batch_assign_{dn_name}"
    
    # Check if already running
    from frappe.utils.background_jobs import is_job_enqueued
    if is_job_enqueued(task_id):
        return {
            "success": True,
            "async": True,
            "task_id": task_id,
            "message": f"Batch assignment for {dn_name} is already in progress."
        }
    
    set_task_status(task_id, "queued")
    
    frappe.enqueue(
        "raven_ai_agent.api.queue_handlers._run_batch_assignment",
        queue="long",
        timeout=600,
        dn_name=dn_name,
        channel_id=channel_id,
        task_id=task_id,
        job_id=task_id,
        deduplicate=True,
        enqueue_after_commit=True
    )
    
    return {
        "success": True,
        "async": True,
        "task_id": task_id,
        "message": f"Batch assignment queued for {dn_name}. Tracking ID: {task_id}"
    }


def _run_batch_assignment(dn_name: str, channel_id: str, task_id: str) -> None:
    """Background worker: Execute batch auto-assignment for a Delivery Note.
    
    This is the actual worker function that runs in the background queue.
    """
    try:
        set_task_status(task_id, "running")
        _publish_progress(channel_id, "batch_assignment", 10,
                         f"Loading DN {dn_name}...", task_id)
        
        dn_doc = frappe.get_doc("Delivery Note", dn_name)
        
        _publish_progress(channel_id, "batch_assignment", 30,
                         f"Analyzing {len(dn_doc.items)} items...", task_id)
        
        # Import the actual batch assignment logic
        from raven_ai_agent.api.smart_delivery import auto_assign_batches
        result = auto_assign_batches(dn_doc)
        
        _publish_progress(channel_id, "batch_assignment", 80,
                         f"Saving DN with {result['assigned']} batch assignments...", task_id)
        
        if result["assigned"] > 0:
            dn_doc.save(ignore_permissions=True)
            frappe.db.commit()
        
        _publish_progress(channel_id, "batch_assignment", 100,
                         "Complete", task_id)
        
        set_task_status(task_id, "completed", result)
        
        # Post result to Raven
        msg = f"Batch assignment complete for **{dn_name}**: {result['assigned']} items assigned."
        if result.get("issues"):
            msg += "\n\nWarnings:\n" + "\n".join(f"  - {i}" for i in result["issues"])
        _send_raven_result(channel_id, msg)
        
    except Exception as e:
        set_task_status(task_id, "failed", {"error": str(e)})
        frappe.log_error(f"Batch assignment failed for {dn_name}: {str(e)}", "RAI Queue")
        _send_raven_result(channel_id,
            f"Batch assignment failed for {dn_name}: {str(e)}")


# =============================================================================
# QUEUED TASK: FULL WORKFLOW (Quotation to Invoice)
# =============================================================================

def enqueue_full_workflow(quotation_name: str, channel_id: str = "",
                          dry_run: bool = False) -> Dict:
    """Enqueue the complete workflow (quotation to invoice) as background job."""
    task_id = f"workflow_{quotation_name}"
    
    from frappe.utils.background_jobs import is_job_enqueued
    if is_job_enqueued(task_id):
        return {
            "success": True,
            "async": True,
            "task_id": task_id,
            "message": f"Workflow for {quotation_name} is already running."
        }
    
    set_task_status(task_id, "queued")
    
    frappe.enqueue(
        "raven_ai_agent.api.queue_handlers._run_full_workflow",
        queue="long",
        timeout=1200,
        quotation_name=quotation_name,
        channel_id=channel_id,
        dry_run=dry_run,
        task_id=task_id,
        job_id=task_id,
        deduplicate=True,
        enqueue_after_commit=True
    )
    
    return {
        "success": True,
        "async": True,
        "task_id": task_id,
        "message": f"{'Dry run' if dry_run else 'Workflow'} queued for {quotation_name}."
    }


def _run_full_workflow(quotation_name: str, channel_id: str,
                       dry_run: bool, task_id: str) -> None:
    """Background worker: Execute the full quotation-to-invoice workflow."""
    try:
        set_task_status(task_id, "running")
        _publish_progress(channel_id, "workflow", 5,
                         f"Starting workflow for {quotation_name}...", task_id)
        
        from raven_ai_agent.api.workflow_executor import WorkflowExecutor
        executor = WorkflowExecutor(
            user=frappe.session.user,
            dry_run=dry_run
        )
        
        result = executor.complete_workflow_to_invoice(quotation_name)
        
        set_task_status(task_id, "completed", result)
        
        # Format result message for Raven
        if result.get("success"):
            msg = f"{'[DRY RUN] ' if dry_run else ''}Workflow complete for {quotation_name}"
            steps = result.get("steps_completed", [])
            if steps:
                msg += "\n\n" + "\n".join(f"  {s}" for s in steps)
        else:
            msg = f"Workflow failed for {quotation_name}: {result.get('error', 'Unknown')}"
        
        _send_raven_result(channel_id, msg)
        
    except Exception as e:
        set_task_status(task_id, "failed", {"error": str(e)})
        frappe.log_error(f"Workflow failed for {quotation_name}: {str(e)}", "RAI Queue")
        _send_raven_result(channel_id,
            f"Workflow failed for {quotation_name}: {str(e)}")


# =============================================================================
# QUEUED TASK: MANUFACTURING STOCK ENTRY
# =============================================================================

def enqueue_manufacture(wo_name: str, channel_id: str = "",
                        qty: float = None) -> Dict:
    """Enqueue a Stock Entry (Manufacture) as background job."""
    task_id = f"manufacture_{wo_name}"
    
    from frappe.utils.background_jobs import is_job_enqueued
    if is_job_enqueued(task_id):
        return {
            "success": True,
            "async": True,
            "task_id": task_id,
            "message": f"Manufacture for {wo_name} is already in progress."
        }
    
    set_task_status(task_id, "queued")
    
    frappe.enqueue(
        "raven_ai_agent.api.queue_handlers._run_manufacture",
        queue="default",
        timeout=600,
        wo_name=wo_name,
        channel_id=channel_id,
        qty=qty,
        task_id=task_id,
        job_id=task_id,
        deduplicate=True,
        enqueue_after_commit=True
    )
    
    return {
        "success": True,
        "async": True,
        "task_id": task_id,
        "message": f"Manufacture queued for {wo_name}."
    }


def _run_manufacture(wo_name: str, channel_id: str,
                     qty: float, task_id: str) -> None:
    """Background worker: Execute Stock Entry (Manufacture)."""
    try:
        set_task_status(task_id, "running")
        
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        mfg = ManufacturingAgent()
        result = mfg.create_stock_entry_manufacture(wo_name, qty=qty)
        
        set_task_status(task_id, "completed", result)
        
        if result.get("success"):
            _send_raven_result(channel_id, result.get("message", "Manufacture complete."))
        else:
            _send_raven_result(channel_id,
                f"Manufacture failed for {wo_name}: {result.get('error', 'Unknown')}")
        
    except Exception as e:
        set_task_status(task_id, "failed", {"error": str(e)})
        frappe.log_error(f"Manufacture failed for {wo_name}: {str(e)}", "RAI Queue")
        _send_raven_result(channel_id,
            f"Manufacture failed for {wo_name}: {str(e)}")
