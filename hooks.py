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
    }
}

# Scheduler
scheduler_events = {
    "daily": [
        "raven_ai_agent.utils.memory.generate_daily_summaries"
    ],
    "cron": {
        # Run at 23:30 daily; wrapper will only act on last day of month
        "30 23 * * *": [
            "raven_ai_agent.cli.batch_pipeline_validation.run_month_end_batch"
        ],
        # Bug Reporter escalation timer — every 5 minutes.  Cheap when there
        # are no paused bugs (single COUNT query); meaningful work only when
        # there are unacknowledged High failures.
        "*/5 * * * *": [
            "raven_ai_agent.bug_reporter.tasks.run_escalation_timer"
        ],
    },
}

# Website
website_route_rules = []

# Fixtures
fixtures = ["AI Agent Settings"]

# ================================================
# ORPHAN DELETION FIX (Frappe GitHub Issue #37799)
# Prevent custom DocTypes from being deleted during bench migrate
# ================================================
override_doctype_class = {
    "IoT Sensor Reading": "raven_ai_agent.raven_ai_agent.doctype.iot_sensor_reading.iot_sensor_reading.IoTSensorReading",
    "IoT Ollama Settings": "raven_ai_agent.raven_ai_agent.doctype.iot_ollama_settings.iot_ollama_settings.IoTOllamaSettings",
    "Alexa User Mapping": "raven_ai_agent.raven_ai_agent.doctype.alexa_user_mapping.alexa_user_mapping.AlexaUserMapping",
    "AI Memory": "raven_ai_agent.raven_ai_agent.doctype.ai_memory.ai_memory.AIMemory",
    "AI Agent Settings": "raven_ai_agent.raven_ai_agent.doctype.ai_agent_settings.ai_agent_settings.AIAgentSettings",
    "Raven Agent Bug": "raven_ai_agent.raven_ai_agent.doctype.raven_agent_bug.raven_agent_bug.RavenAgentBug",
    "Raven Agent Bug Occurrence": "raven_ai_agent.raven_ai_agent.doctype.raven_agent_bug_occurrence.raven_agent_bug_occurrence.RavenAgentBugOccurrence",
}

# Run workspace orphan fix before migration
before_migrate = ["amb_w_tds.patches.fix_workspace_orphan.apply_patch"]
