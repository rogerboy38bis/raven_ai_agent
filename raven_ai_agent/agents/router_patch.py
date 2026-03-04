"""
Router — PATCH for handle_raven_message

This shows ONLY the new routing entries to add to the existing router.py
in raven_ai_agent/api/handlers/router.py.

Add these elif blocks inside the handle_raven_message function,
BEFORE the fallback to SkillRouter/RaymondLucyAgent.
"""

# ============================================================
# ADD THESE ELIF BLOCKS in handle_raven_message()
# After the existing @iot check and before the `else:` fallback
# ============================================================

# --- NEW: @manufacturing bot ---
# Check for @manufacturing bot
# elif "manufacturing" in plain_text.lower():
#     query = plain_text.lower().replace("@manufacturing", "").strip()
#     if not query:
#         query = "help"
#     bot_name = "manufacturing"

# --- NEW: @payment bot ---
# elif "payment" in plain_text.lower():
#     query = plain_text.lower().replace("@payment", "").strip()
#     if not query:
#         query = "help"
#     bot_name = "payment"

# --- NEW: @workflow bot ---
# elif "workflow" in plain_text.lower():
#     query = plain_text.lower().replace("@workflow", "").strip()
#     if not query:
#         query = "help"
#     bot_name = "workflow"

# ============================================================
# ADD THESE ELIF BLOCKS in the agent routing section
# After: elif bot_name == "iot":
# Before: else: (SkillRouter fallback)
# ============================================================

# elif bot_name == "manufacturing":
#     from raven_ai_agent.agents import ManufacturingAgent
#     mfg_agent = ManufacturingAgent(user)
#     response = mfg_agent.process_command(query)
#     result = {"success": True, "response": response}
# elif bot_name == "payment":
#     from raven_ai_agent.agents import PaymentAgent
#     pay_agent = PaymentAgent(user)
#     response = pay_agent.process_command(query)
#     result = {"success": True, "response": response}
# elif bot_name == "workflow":
#     from raven_ai_agent.agents import WorkflowOrchestrator
#     wf_agent = WorkflowOrchestrator(user)
#     response = wf_agent.process_command(query)
#     result = {"success": True, "response": response}
