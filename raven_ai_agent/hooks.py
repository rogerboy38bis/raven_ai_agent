app_name = "raven_ai_agent"
app_title = "Raven AI Agent"
app_publisher = "Your Company"
app_description = "Raymond-Lucy AI Agent for ERPNext - Anti-Hallucination + Persistent Memory"
app_email = "your@email.com"
app_license = "MIT"
required_apps = ["frappe"]

# App includes (required for build)
# app_include_css = "/assets/raven_ai_agent/css/raven_ai_agent.css"
# app_include_js = "/assets/raven_ai_agent/js/raven_ai_agent.js"

# Doctype-specific JS 
# Note: Multiple JS files for same doctype should be combined or use app_include_js
doctype_js = {
    "Sales Order": "raven_ai_agent/public/js/sales_order_upload.js",
    "Sales Invoice": "raven_ai_agent/public/js/sales_invoice_upload.js"
}

# App-level JS (includes Phase 10.4 Documents Panel)
app_include_js = "/assets/raven_ai_agent/js/documents_panel.js"

# Hooks
doc_events = {
    "Raven Message": {
        "after_insert": "raven_ai_agent.api.agent.handle_raven_message"
    },
    "File": {
        "after_insert": "raven_ai_agent.api.po_extractor.on_file_added"
    }
}

# App lifecycle hooks
def post_install():
    """Create custom fields after app install"""
    from raven_ai_agent.api.custom_fields import create_po_extraction_fields, create_pedimento_fields
    create_po_extraction_fields()
    create_pedimento_fields()

def app_install():
    """Create custom fields on app install"""
    from raven_ai_agent.api.custom_fields import create_po_extraction_fields, create_pedimento_fields
    create_po_extraction_fields()
    create_pedimento_fields()

def app_uninstall():
    """Clean up custom fields on app uninstall"""
    from raven_ai_agent.api.custom_fields import delete_po_extraction_fields, delete_pedimento_fields
    delete_po_extraction_fields()
    delete_pedimento_fields()

# Scheduler
scheduler_events = {
    "daily": [
        "raven_ai_agent.utils.memory.generate_daily_summaries"
    ]
}

# Website
website_route_rules = []

# Fixtures (disabled temporarily)
# fixtures = ["AI Agent Settings"]
fixtures = ["IoT Ollama Settings"]

# Commands (Phase 10.3 - Bulk Import)
from raven_ai_agent.commands.drive_import import commands
command = commands
