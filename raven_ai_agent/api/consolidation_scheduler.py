"""
Consolidation Agent Scheduler Events
Setup timer-based consolidation

Run this to enable automatic memory consolidation every 30 minutes
"""
import frappe
from raven_ai_agent.api.consolidation_agent import run_consolidation_job


def setup_consolidation_scheduler():
    """
    Create a scheduled job for memory consolidation
    
    This sets up the consolidation agent to run every 30 minutes
    """
    
    # Create scheduler event if it doesn't exist
    if not frappe.db.exists("Scheduled Job Type", {
        "method": "raven_ai_agent.api.consolidation_agent.run_consolidation_job"
    }):
        doc = frappe.get_doc({
            "doctype": "Scheduled Job Type",
            "method": "raven_ai_agent.api.consolidation_agent.run_consolidation_job",
            "frequency": "Cron",
            "cron_format": "*/30 * * * *",  # Every 30 minutes
            "enabled": 1,
            "server_script": None
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        print("✅ Scheduler job created: memory consolidation every 30 minutes")
    else:
        print("ℹ️ Scheduler job already exists")
    
    # Also create a simpler approach using frappe.call_after
    # This is useful for testing
    
    return {
        "status": "setup_complete",
        "schedule": "Every 30 minutes",
        "method": "raven_ai_agent.api.consolidation_agent.run_consolidation_job"
    }


def run_manual_consolidation(user=None):
    """
    Run consolidation manually
    
    Usage:
    bench console
    exec(open('consolidation_scheduler.py').read())
    result = run_manual_consolidation("user@email.com")
    """
    from raven_ai_agent.api.consolidation_agent import ConsolidationAgent
    
    agent = ConsolidationAgent(user=user)
    result = agent.run_consolidation(user=user)
    
    print(f"Consolidation result: {result}")
    return result


def disable_consolidation_scheduler():
    """Disable the consolidation scheduler"""
    job = frappe.db.get_value("Scheduled Job Type", 
        {"method": "raven_ai_agent.api.consolidation_agent.run_consolidation_job"},
        "name")
    
    if job:
        frappe.db.set_value("Scheduled Job Type", job, "enabled", 0)
        frappe.db.commit()
        print("✅ Consolidation scheduler disabled")
    else:
        print("ℹ️ No scheduler job found")


# Auto-setup when imported
if __name__ != "__main__":
    # Only auto-setup in ERPNext context
    try:
        frappe.flags.in_test
    except:
        pass
