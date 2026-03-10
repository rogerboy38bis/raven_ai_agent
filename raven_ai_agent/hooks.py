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

# Hooks
doc_events = {
    "Raven Message": {
        "after_insert": "raven_ai_agent.api.agent.handle_raven_message"
    },
    "File": {
        "after_insert": "raven_ai_agent.api.po_extractor.on_file_added"
    }
}

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
