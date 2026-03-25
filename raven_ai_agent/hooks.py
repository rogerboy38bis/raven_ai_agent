app_name = "raven_ai_agent"
app_title = "Raven AI Agent"
app_publisher = "Your Company"
app_description = "Raymond-Lucy AI Agent for ERPNext - Anti-Hallucination + Persistent Memory"
app_email = "your@email.com"
app_license = "MIT"
required_apps = ["frappe"]

# App includes (required for build)
# BUG 80C: Switched from doctype_js to app_include_js to avoid bench build in Docker
app_include_js = [
    "/assets/raven_ai_agent/js/raven_ai_agent.js",
    "raven_ai_agent/public/js/sales_order_upload.js",
    "raven_ai_agent/public/js/sales_invoice_upload.js",
    "raven_ai_agent/public/js/documents_panel.js"
]

# Commented out doctype_js - not used (switched to app_include_js for Docker compatibility)
# doctype_js = {
#     "Sales Order": [
#         "raven_ai_agent/public/js/sales_order_upload.js",
#         "raven_ai_agent/public/js/documents_panel.js"
#     ],
#     "Sales Invoice": [
#         "raven_ai_agent/public/js/sales_invoice_upload.js",
#         "raven_ai_agent/public/js/documents_panel.js"
#     ]
# }

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
    print("[raven_ai_agent] Running post_install...")
    from raven_ai_agent.api.custom_fields import create_po_extraction_fields, create_pedimento_fields
    create_po_extraction_fields()
    create_pedimento_fields()
    print("[raven_ai_agent] post_install complete.")

def app_install():
    """Create custom fields on app install"""
    print("[raven_ai_agent] Running app_install...")
    from raven_ai_agent.api.custom_fields import create_po_extraction_fields, create_pedimento_fields
    create_po_extraction_fields()
    create_pedimento_fields()
    print("[raven_ai_agent] app_install complete.")

def after_install(app=None):
    """Create custom fields after app is installed (runs for each site)"""
    print("[raven_ai_agent] Running after_install...")
    from raven_ai_agent.api.custom_fields import create_po_extraction_fields, create_pedimento_fields
    create_po_extraction_fields()
    create_pedimento_fields()
    print("[raven_ai_agent] after_install complete.")

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
# Note: Commands are registered via the commands directory in the app
# bench command is auto-discovered from app/commands folder
