"""
Router - Message handling and bot routing

Contains the @frappe.whitelist() entry points:
- process_message: API endpoint for processing messages
- handle_raven_message: Webhook handler for Raven messages with bot routing

Updated 2026-03-03: Added manufacturing, payment, and orchestrator agent routing
Updated 2026-03-13: Added response post-processing for consistent formatting
"""
import frappe
import json
import re
from typing import Optional, Dict, List

# Import response formatter for post-processing
from raven_ai_agent.api.response_formatter import apply_post_processing

@frappe.whitelist()
def process_message(message: str, conversation_history: str = None) -> Dict:
    """API endpoint for processing messages"""
    user = frappe.session.user
    agent = RaymondLucyAgent(user)
    
    history = json.loads(conversation_history) if conversation_history else []
    
    return agent.process_query(message, history)


def _detect_ai_intent(query: str) -> str:
    """
    Detect which agent should handle an @ai command based on keywords/patterns.
    
    Returns bot_name: manufacturing_bot, payment_bot, workflow_orchestrator,
                      sales_order_follow_up, or sales_order_bot (default)
    """
    query_lower = query.lower()

    # === PRIORITY: Help commands - route to sales_order_bot ===
    if query_lower.startswith("help") or query_lower.startswith("ayuda"):
        return "sales_order_bot"

    # === PRIORITY: Task Validator commands (check data, pipeline, fix, diagnose) ===
    # These must come BEFORE diagnosis_commands to route to sales_order_bot instead of scanner
    if re.search(r'^check\s+data\s+SAL-QTN-', query, re.IGNORECASE):
        return "sales_order_bot"
    if re.search(r'^pipeline\s+SAL-QTN-', query, re.IGNORECASE):
        return "sales_order_bot"
    if re.search(r'^fix\s+SAL-QTN-', query, re.IGNORECASE):
        return "sales_order_bot"
    if re.search(r'^fix\s+SO-', query, re.IGNORECASE):
        return "sales_order_bot"
    if re.search(r'^diagnose\s+SAL-QTN-', query, re.IGNORECASE):
        return "sales_order_bot"
    # Bug 62 fix: Route diagnose SO- to sales_order_follow_up (not old sales_order_bot)
    # The old sales_order_bot returns placeholder text; sales_order_follow_up has full functionality
    if re.search(r'^diagnose\s+SO-', query, re.IGNORECASE):
        return "sales_order_follow_up"

    # === PRIORITY: Data Quality Scanner / Diagnosis commands ===
    # These commands should ALWAYS go to the skills system, NOT sales_order_follow_up
    diagnosis_commands = [
        r'^scan\s+SO-',          # @ai scan SO-00752
        r'^scan\s+SAL-QTN-',     # @ai scan SAL-QTN-2024-00752
        r'^validate\s+SO-',       # @ai validate SO-00752
        r'^check\s+data\s+SO-',  # @ai check data SO-00752
        r'pipeline\s+SO-',       # @ai pipeline SO-00752
        r'pipeline\s+SAL-QTN-',  # @ai pipeline SAL-QTN-2024-00752
        r'full\s+scan\s+SO-',    # @ai full scan SO-00752
        # === Quotation Diagnostics (NEW) ===
        r'diagnose\s+pipeline\s+of\s+quotation',  # @ai diagnose pipeline of quotation
        r'diagnose\s+quotation',   # @ai diagnose quotation QUOT-XXX or SAL-QTN-XXX
        r'diagnose\s+SAL-QTN-',    # @ai diagnose SAL-QTN-2024-00752 (direct)
        r'diagnose\s+QUOT-',       # @ai diagnose QUOT-2026-00001 (direct)
        r'scan\s+quotation',       # @ai scan quotation QUOT-XXX or SAL-QTN-XXX
        r'scan\s+SAL-QTN-',        # @ai scan SAL-QTN-2024-00752 (direct)
        r'pipeline\s+quotation',   # @ai pipeline quotation QUOT-XXX
        r'pipeline\s+SAL-QTN-',     # @ai pipeline SAL-QTN-2024-00752 (direct)
        r'validate\s+quotation',   # @ai validate quotation QUOT-XXX
        r'QUOT-\d+-\d+',          # Matches QUOT-2026-00001
    ]
    if any(re.search(p, query, re.IGNORECASE) for p in diagnosis_commands):
        return "data_quality_scanner"
    
    # === PRIORITY: SO-linked commands always go to sales agent ===
    # BUT: pipeline/diagnose commands for SAL-QTN should go to data_quality_scanner
    if re.search(r'SO-\d+', query, re.IGNORECASE) or re.search(r'from\s+SO', query, re.IGNORECASE):
        # Exception: if it's a pipeline/diagnose command, send to scanner instead
        if re.search(r'(?:pipeline|diagnose|scan)\s+SO-', query, re.IGNORECASE):
            return "data_quality_scanner"
        elif not re.search(r'(?:reconcile|submit\s+ACC-PAY|ACC-PAY-\d+)', query, re.IGNORECASE):
            return "sales_order_follow_up"
    
    # === PRIORITY: SAL-QTN pipeline/diagnose goes to data_quality_scanner ===
    if re.search(r'(?:pipeline|diagnose|scan|validate)\s+SAL-QTN-', query, re.IGNORECASE):
        return "data_quality_scanner"
    
    # === PRIORITY: SAL-QTN standalone (without prefix) also goes to scanner ===
    if re.search(r'SAL-QTN-\d+-\d+', query, re.IGNORECASE):
        # Check if it's a pipeline/diagnose/scan command
        if any(kw in query.lower() for kw in ['pipeline', 'diagnose', 'scan', 'validate', 'fix']):
            return "data_quality_scanner"
    
    # Orchestrator: pipeline, full cycle, validate, dry run
    orch_patterns = [
        r'pipeline\s+status',
        r'(?:run|start)\s+full\s+cycle',
        r'dry\s+run',
        r'validate\s+SO-',
        r'run\s+pipeline',
    ]
    if any(re.search(p, query, re.IGNORECASE) for p in orch_patterns):
        return "workflow_orchestrator"
    
    # Manufacturing Agent: work order, WO, manufacture, transfer, MFG-WO-
    mfg_patterns = [
        r'MFG-WO-\d+',
        r'(?:create|make)\s+work\s*order',
        r'submit\s+MFG',
        r'transfer\s+material',
        r'(?:manufacture|finish|produce)\s+MFG',
        r'(?:list|show)\s+work\s*orders?',
        r'(?:create|make)\s+wo\b',
        r'(?:status|check)\s+MFG-WO',
        r'wo\s+plan\b',
        r'create\s+batch\b',
        r'mis\s+ordenes',
    ]
    if any(re.search(p, query, re.IGNORECASE) for p in mfg_patterns):
        return "manufacturing_bot"
    
    # Payment Agent: payment, pay, ACC-SINV, ACC-PAY, unpaid, outstanding
    pay_patterns = [
        r'ACC-SINV-\d+',
        r'ACC-PAY-\d+',
        r'SINV-\d+',
        r'(?:create|make)\s+payment',
        r'submit\s+ACC-PAY',
        r'reconcile\s+ACC-PAY',
        r'unpaid\s+invoices?',
        r'outstanding',
    ]
    if any(re.search(p, query, re.IGNORECASE) for p in pay_patterns):
        return "payment_bot"
    
    # Task Validator / Diagnosis: diagnose, validate, audit pipeline, check payments
    # Also handles fix commands for data quality issues
    validator_patterns = [
        r'diagnos[ei]',
        r'validate\b',
        r'audit\s+pipeline',
        r'check\s+payment',
        r'check\s+pago',
        r'pipeline\s+health',
        r'verify\s+(?:SO|sales\s+order)',
        r'^fix\s+SO-',           # @ai fix SO-00752
        r'^scan\s+SO-',          # @ai scan SO-00752
    ]
    if any(re.search(p, query, re.IGNORECASE) for p in validator_patterns):
        return "sales_order_bot"
    
    # Party Account Management (NEW)
    party_account_patterns = [
        r'create\s+party\s+accounts',
        r'party\s+account',
        r'fix\s+customer\s+account',
        r'assign\s+customer\s+account',
        r'batch\s+account',
    ]
    if any(re.search(p, query, re.IGNORECASE) for p in party_account_patterns):
        return "sales_order_bot"
    
    # Sales-specific patterns (DN, invoice, pending orders, next steps)
    sales_patterns = [
        r'(?:create|make)\s+(?:DN|delivery\s*note)',
        r'(?:create|make)\s+(?:sales\s+)?invoice',
        r'(?:create|make)\s+SO\s+from',
        r'pending\s+orders?',
        r'next\s+steps?',
        r'(?:status|check)\s+SO-',
        r'inventory\s+SO-',
        r'track\s+purchase',
        r'!create\s+',
        r'(?:create|make)\s+(?:sales\s+)?(?:invoice|SI)\s+(?:from|for)',
    ]
    if any(re.search(p, query, re.IGNORECASE) for p in sales_patterns):
        return "sales_order_follow_up"
    
    # Default
    return "sales_order_bot"


@frappe.whitelist()
def handle_raven_message(doc=None, method=None):
    """Hook for Raven message integration - handles @ai and @bot_name mentions in any channel
    
    Args:
        doc: Raven Message document or document name (for after_insert hook or direct call)
        method: The method that triggered the hook (e.g., "after_insert")
    """
    from bs4 import BeautifulSoup
    
    try:
        # Handle direct call with message name string instead of doc object
        if isinstance(doc, str):
            doc_name = doc
            doc = frappe.get_doc("Raven Message", doc_name)
        
        # Skip bot messages to avoid infinite loops
        if doc.is_bot_message:
            return
        
        if not doc.text:
            return
        
        # Strip HTML to get plain text (Raven wraps messages in <p> tags)
        plain_text = BeautifulSoup(doc.text, "html.parser").get_text().strip()
        
        frappe.logger().info(f"[AI Agent] Raw text: {doc.text[:100]}")
        frappe.logger().info(f"[AI Agent] Plain text: {plain_text[:100]}")
        
        query = None
        bot_name = None
        
        # Check for @ai trigger — uses intent detection to route to correct agent
        if plain_text.lower().startswith("@ai"):
            query = plain_text[3:].strip()
            
            # Phase 7: Try intent resolution for natural language
            resolved_command = None
            try:
                from raven_ai_agent.api.intent_resolver import resolve_intent_message
                resolved_command = resolve_intent_message(query)
                if resolved_command:
                    frappe.logger().info(f"[IntentResolver] Using resolved command: {resolved_command}")
                    query = resolved_command
            except Exception as e:
                frappe.logger().warning(f"[IntentResolver] Resolution failed, using raw query: {e}")
            
            bot_name = _detect_ai_intent(query)
            frappe.logger().info(f"[AI Agent] @ai intent detected: {bot_name}")
        
        # Check for @sales_order_bot mention
        elif "sales_order_bot" in plain_text.lower():
            query = plain_text.replace("@sales_order_bot", "").strip()
            if not query:
                query = "help"
            bot_name = "sales_order_bot"
        
        # Check for @sales_order_follow_up bot
        elif "sales_order_follow_up" in plain_text.lower():
            query = plain_text.lower().replace("@sales_order_follow_up", "").strip()
            if not query:
                query = "help"
            bot_name = "sales_order_follow_up"
        
        # Check for @manufacturing or @mfg bot
        elif "manufacturing" in plain_text.lower() or "@mfg" in plain_text.lower():
            query = re.sub(r'@(?:manufacturing|mfg)\s*', '', plain_text, flags=re.IGNORECASE).strip()
            if not query:
                query = "help"
            bot_name = "manufacturing_bot"
        
        # Check for @payment bot (also handles @ai payment)
        if re.match(r'^@ai\s+payment', plain_text, re.IGNORECASE):
            # Handle @ai payment commands - strip both @ai and payment
            query = re.sub(r'^@ai\s+payment\s*', '', plain_text, flags=re.IGNORECASE).strip()
            if not query:
                query = "help"
            bot_name = "payment_bot"
        elif "payment" in plain_text.lower() and plain_text.lower().startswith("@"):
            query = re.sub(r'@payment\s*', '', plain_text, flags=re.IGNORECASE).strip()
            if not query:
                query = "help"
            bot_name = "payment_bot"
        
        # Check for @orchestrator or @pipeline bot
        elif "orchestrator" in plain_text.lower() or "@pipeline" in plain_text.lower():
            query = re.sub(r'@(?:orchestrator|pipeline)\s*', '', plain_text, flags=re.IGNORECASE).strip()
            if not query:
                query = "help"
            bot_name = "workflow_orchestrator"
        
        # Check for @rnd_bot
        elif "rnd_bot" in plain_text.lower():
            query = plain_text.lower().replace("@rnd_bot", "").strip()
            if not query:
                query = "help"
            bot_name = "rnd_bot"
        
        # Check for @executive bot
        elif "executive" in plain_text.lower():
            query = plain_text.lower().replace("@executive", "").strip()
            if not query:
                query = "helicopter"
            bot_name = "executive"

        # Check for @iot bot
        elif "iot" in plain_text.lower():
            query = plain_text.lower().replace("@iot", "").strip()
            if not query:
                query = "help"
            bot_name = "iot"
        
        if not query:
            return
        
        user = doc.owner
        frappe.logger().info(f"[AI Agent] Processing query from {user}: {query}")
        
        # Use ignore_permissions flag instead of switching user (avoids logout issue)
        original_ignore = frappe.flags.ignore_permissions
        try:
            frappe.flags.ignore_permissions = True
            
            # === Route to specialized agent based on bot_name ===
            
            # NEW: Manufacturing Agent
            if bot_name == "manufacturing_bot":
                from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
                mfg_agent = ManufacturingAgent()
                response = mfg_agent.process_command(query)
                result = {"success": True, "response": response}
            
            # NEW: Payment Agent
            elif bot_name == "payment_bot":
                from raven_ai_agent.agents.payment_agent import PaymentAgent
                pay_agent = PaymentAgent()
                response = pay_agent.process_command(query)
                result = {"success": True, "response": response}
            
            # NEW: Workflow Orchestrator
            elif bot_name == "workflow_orchestrator":
                from raven_ai_agent.agents.workflow_orchestrator import WorkflowOrchestrator
                orch_agent = WorkflowOrchestrator()
                response = orch_agent.process_command(query)
                result = {"success": True, "response": response}
            
            # NEW: Task Validator / Diagnosis Agent
            elif bot_name == "sales_order_bot":
                from raven_ai_agent.agents.sales_order_bot import TaskValidatorMixin
                # Create a lightweight wrapper to use the mixin
                class _ValidatorAgent(TaskValidatorMixin):
                    pass
                validator = _ValidatorAgent()
                validator_result = validator._handle_validator_commands(query, query.lower())
                if validator_result:
                    result = {"success": True, "response": validator_result.get("message") or validator_result.get("error", "No result")}
                else:
                    result = {"success": False, "response": "Could not process validator command. Try: `@ai diagnose SAL-QTN-XXXX`"}
            
            # EXISTING: Sales Order Follow-up
            elif bot_name == "sales_order_follow_up":
                from raven_ai_agent.agents import SalesOrderFollowupAgent
                so_agent = SalesOrderFollowupAgent(user)
                response = so_agent.process_command(query)
                result = {"success": True, "response": response}
            
            # EXISTING: R&D Agent
            elif bot_name == "rnd_bot":
                from raven_ai_agent.agents import RnDAgent
                rnd_agent = RnDAgent(user)
                response = rnd_agent.process_command(query)
                result = {"success": True, "response": response}
            
            # EXISTING: Executive Agent
            elif bot_name == "executive":
                from raven_ai_agent.agents.executive_agent import ExecutiveAgent
                exec_agent = ExecutiveAgent(user)
                response = exec_agent.process_command(query)
                result = {"success": True, "response": response}
            
            # EXISTING: IoT Agent
            elif bot_name == "iot":
                from raven_ai_agent.agents.iot_agent import IoTAgent
                iot_agent = IoTAgent(user)
                result = iot_agent.process_command(query)
            
            # DEFAULT: SkillRouter → RaymondLucyAgent fallback
            else:
                try:
                    from raven_ai_agent.skills.router import SkillRouter
                    router = SkillRouter()
                    router_result = router.route(query)
                    if router_result and router_result.get("handled"):
                        result = {"success": True, "response": router_result.get("response", "Skill executed.")}
                    else:
                        agent = RaymondLucyAgent(user)
                        result = agent.process_query(query)
                except ImportError:
                    frappe.logger().warning("[AI Agent] SkillRouter not available, using default agent")
                    agent = RaymondLucyAgent(user)
                    result = agent.process_query(query)
        finally:
            frappe.flags.ignore_permissions = original_ignore
        
        frappe.logger().info(f"[AI Agent] Result: success={result.get('success')}")
        
        # Get bot for proper message sending
        bot = None
        if bot_name:
            try:
                bot = frappe.get_doc("Raven Bot", bot_name)
            except frappe.DoesNotExistError:
                frappe.logger().warning(f"[AI Agent] Bot {bot_name} not found, trying sales_order_bot")
                try:
                    bot = frappe.get_doc("Raven Bot", "sales_order_bot")
                except frappe.DoesNotExistError:
                    frappe.logger().warning("[AI Agent] No bot found, using direct message")
        
        response_text = result.get("response") or result.get("message") or result.get("error") or "No response generated"
        
        # Apply post-processing for consistent formatting
        response_text = apply_post_processing(response_text)
        
        link_doctype = result.get("link_doctype")
        link_document = result.get("link_document")
        
        if bot:
            bot.send_message(
                channel_id=doc.channel_id,
                text=response_text,
                markdown=True,
                link_doctype=link_doctype,
                link_document=link_document
            )
        else:
            # Fallback: create message directly
            reply_doc = frappe.get_doc({
                "doctype": "Raven Message",
                "channel_id": doc.channel_id,
                "text": response_text,
                "message_type": "Text",
                "is_bot_message": 1
            })
            reply_doc.insert(ignore_permissions=True)
            frappe.db.commit()
            
            # Publish realtime event to notify frontend clients
            publish_message_created_event(reply_doc, doc.channel_id)
            frappe.logger().info(f"[AI Agent] Published realtime event for channel {doc.channel_id}")
        
        frappe.logger().info(f"[AI Agent] Reply sent to channel {doc.channel_id}")
        
    except Exception as e:
        frappe.logger().error(f"[AI Agent] Error: {str(e)}")
        frappe.log_error(f"AI Agent Error: {str(e)}", "Raven AI Agent")
        try:
            error_doc = frappe.get_doc({
                "doctype": "Raven Message",
                "channel_id": doc.channel_id,
                "text": f"\u274c Error: {str(e)}",
                "message_type": "Text",
                "is_bot_message": 1
            })
            error_doc.insert(ignore_permissions=True)
            frappe.db.commit()
            
            # Publish realtime event for error message too
            publish_message_created_event(error_doc, doc.channel_id)
        except:
            pass
