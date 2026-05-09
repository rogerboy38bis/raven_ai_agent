from frappe import _

def get_data():
    return [
        {
            "module_name": "AI Orchestrator",
            "type": "module",
            "label": _("AI Orchestrator"),
            "icon": "octicon octicon-robot",
            "color": "blue",
            "description": _("Multi-agent orchestration layer for ERPNext"),
        }
    ]
