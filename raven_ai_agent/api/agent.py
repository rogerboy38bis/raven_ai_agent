"""
Raymond-Lucy AI Agent Core
Phase 2+3: Split from monolithic agent.py + Quality Management System

Module map:
  agent_prompts.py   — SYSTEM_PROMPT, CAPABILITIES_LIST (199 lines)
  memory_manager.py  — MemoryMixin: briefing, memory search, fact storage (142 lines)
  context_builder.py — ContextMixin: doctype detection, web search, ERPNext context (471 lines)
  command_router.py  — CommandRouterMixin: autonomy + workflow dispatch (245 lines)
  agent.py (this)    — RaymondLucyAgent class composition + API entry points (~280 lines)

Phase 3 additions:
  handlers/quality_management.py — QualityManagementMixin: NC, CAPA, SOP, Audit, KPI, Training (736 lines)

Phase 4 additions:
  handlers/analytics.py — AnalyticsMixin: Dashboards, Trends, Reports, Alerts (943 lines)

Backward compatibility:
  - All @frappe.whitelist() endpoints preserved
  - RaymondLucyAgent class still importable from this module
  - Handler mixins (ManufacturingMixin, BOMMixin, etc.) still inherited
"""
import frappe
import json
import re
from typing import Optional, Dict, List
from openai import OpenAI

# Import channel utilities for realtime events
from raven_ai_agent.api.channel_utils import publish_message_created_event

# Import split modules
from raven_ai_agent.api.agent_prompts import SYSTEM_PROMPT, CAPABILITIES_LIST
from raven_ai_agent.api.memory_manager import MemoryMixin
from raven_ai_agent.api.context_builder import ContextMixin
from raven_ai_agent.api.command_router import CommandRouterMixin

# Import handler mixins (Phase 1 + Phase 3 QMS)
from raven_ai_agent.api.handlers import (
    ManufacturingMixin,
    BOMMixin,
    WebSearchMixin,
    SalesMixin,
    QuotationMixin,
    QualityManagementMixin,
    AnalyticsMixin,
)

SYSTEM_PROMPT = """
You are an AI assistant for ERPNext operating under the "Raymond-Lucy Protocol v2.0".

## ARCHITECTURE: LLM OS MODEL
- Context Window = RAM (limited, resets each session)
- Vector DB = Hard Drive (persistent memory via AI Memory doctype)
- Tools = ERPNext APIs and Frappe framework

## CORE PRINCIPLES

### 1. RAYMOND PROTOCOL (Anti-Hallucination)
- NEVER fabricate ERPNext data - always query the database
- ALWAYS cite document names and field values
- EXPRESS confidence: HIGH/MEDIUM/LOW/UNCERTAIN
- Use frappe.db queries to verify facts

### 2. MEMENTO PROTOCOL (Fact Storage)
Store important facts about user preferences and context:
- CRITICAL: User roles, permissions, company context
- HIGH: Recent transactions, workflow states
- NORMAL: Preferences, past queries

### 3. LUCY PROTOCOL (Context Continuity)
- Load user's morning briefing at session start
- Reference past conversations naturally
- Generate session summaries

### 4. KARPATHY PROTOCOL (Autonomy Slider)
- LEVEL 1 (COPILOT): Suggest, explain, query data
- LEVEL 2 (COMMAND): Execute specific operations with confirmation
- LEVEL 3 (AGENT): Multi-step workflows (requires explicit permission)

## ERPNEXT SPECIFIC RULES
1. Always verify doctypes exist before querying
2. Check user permissions before showing sensitive data
3. Use frappe.get_doc() for single documents
4. Use frappe.get_list() for multiple documents
5. Format currency/dates according to user's locale

## RESPONSE FORMAT
[CONFIDENCE: HIGH/MEDIUM/LOW/UNCERTAIN] [AUTONOMY: LEVEL 1/2/3]

{Your response - be concise and actionable}

When showing documents:
- Include clickable links if provided in context
- Format as a clean list with key info (name, customer/party, amount, date, status)
- Use markdown formatting for clarity

## EXTERNAL WEB ACCESS
- You CAN fetch data from external URLs if the user provides a specific URL in their query
- Example: "find address from http://www.barentz.com/contact" will fetch that website's content
- You CAN also do web searches without URLs using keywords like "search", "find", "look up"
- Example: "search for barentz italia address" will search the web and return results
- When web search results are provided, summarize the relevant information for the user

## DYNAMIC DATA ACCESS
- You have access to any ERPNext doctype the user has permission to view
- The system auto-detects which doctypes are relevant based on keywords in the query
- If no data is found, it means either no records exist or user lacks permission

## CRITICAL RULES - MUST FOLLOW
- NEVER say "hold on", "please wait", "let me check", "searching now", "I will perform" - you CANNOT do follow-up queries
- NEVER promise to search or fetch data - the search has ALREADY been done BEFORE your response
- If you see "⭐ WEB SEARCH RESULTS" or "⭐ EXTERNAL WEB DATA" in context, IMMEDIATELY extract and present the information
- ALWAYS assume LEVEL 1 for read-only queries about addresses, contacts, websites, or any information lookup
- Do NOT ask "Would you like to proceed with a web search?" - the search is ALREADY DONE
- Extract and present the relevant information from the provided context
- If data is not in the provided context, say "I don't have that data available"

[Sources: Document names queried]
"""


class RaymondLucyAgent(
    MemoryMixin,
    ContextMixin,
    CommandRouterMixin,
    ManufacturingMixin,
    BOMMixin,
    WebSearchMixin,
    SalesMixin,
    QuotationMixin,
    QualityManagementMixin,
    AnalyticsMixin,
):
    """
    Raymond-Lucy AI Agent - ERPNext AI Assistant
    Anti-Hallucination + Persistent Memory + Autonomy Slider

    Composed from handler mixins for modularity:
    - MemoryMixin: Morning briefing, memory search, fact storage (142 lines)
    - ContextMixin: Doctype detection, web search, ERPNext context (471 lines)
    - CommandRouterMixin: Autonomy + workflow command dispatch (245 lines)
    - ManufacturingMixin: Manufacturing SOP + Stock Entry (606 lines)
    - BOMMixin: BOM commands + label fixer + cancel (267 lines)
    - WebSearchMixin: Direct web search (53 lines)
    - SalesMixin: Sales-to-Purchase cycle (477 lines)
    - QuotationMixin: Quotation fix + update + TDS (415 lines)
    - QualityManagementMixin: NC, CAPA, SOP, Audit, KPI, Training (736 lines) [Phase 3]
    - AnalyticsMixin: Dashboards, Trends, Reports, Alerts (943 lines) [Phase 4]
    """

    def __init__(self, user: str):
        self.user = user
        self.settings = self._get_settings()
        self.client = OpenAI(api_key=self.settings.get("openai_api_key"))
        self.model = self.settings.get("model", "gpt-4o-mini")
        self.autonomy_level = 1  # Default to COPILOT

    def _get_settings(self) -> Dict:
        """Load AI Agent Settings - tries multiple sources"""
        # Try 1: Our AI Agent Settings doctype
        try:
            settings = frappe.get_single("AI Agent Settings")
            api_key = settings.get_password("openai_api_key")
            if api_key:
                return {
                    "openai_api_key": api_key,
                    "model": settings.model or "gpt-4o-mini",
                    "max_tokens": settings.max_tokens or 2000,
                    "confidence_threshold": settings.confidence_threshold or 0.7
                }
        except Exception:
            pass

        # Try 2: Raven's AI Settings (Raven Settings doctype)
        try:
            raven_settings = frappe.get_single("Raven Settings")
            api_key = raven_settings.get_password("openai_api_key")
            if api_key:
                return {
                    "openai_api_key": api_key,
                    "model": "gpt-4o-mini",
                    "max_tokens": 2000,
                    "confidence_threshold": 0.7
                }
        except Exception:
            pass

        # Try 3: Site config fallback
        api_key = frappe.conf.get("openai_api_key")
        if api_key:
            return {
                "openai_api_key": api_key,
                "model": "gpt-4o-mini",
                "max_tokens": 2000,
                "confidence_threshold": 0.7
            }

        return {}

    def process_query(self, query: str, conversation_history: List[Dict] = None, channel_id: str = "") -> Dict:
        """Main processing function"""

        query_lower = query.lower()

        # Handle help/capabilities command
        if any(h in query_lower for h in ["help", "capabilities", "what can you do", "que puedes hacer", "ayuda"]):
            return {
                "success": True,
                "response": f"[CONFIDENCE: HIGH] [AUTONOMY: LEVEL 1]\n{CAPABILITIES_LIST}",
                "autonomy_level": 1,
                "context_used": {"help": True}
            }

        # Determine autonomy level
        suggested_autonomy = self.determine_autonomy(query)

        # Try workflow command first (Level 2/3 operations)
        is_force = query.startswith("!")
        clean_query = query.lstrip("!").strip() if is_force else query

        workflow_result = self.execute_workflow_command(clean_query, channel_id=channel_id)
        if workflow_result:
            # With ! prefix, execute directly without confirmation
            if is_force:
                if workflow_result.get("requires_confirmation") or workflow_result.get("preview"):
                    workflow_result = self.execute_workflow_command(clean_query, channel_id=channel_id, confirm=True)

                if workflow_result.get("success"):
                    return {
                        "success": True,
                        "response": f"[CONFIDENCE: HIGH] [AUTONOMY: LEVEL 2]\n\n{workflow_result.get('message', 'Operation completed.')}",
                        "autonomy_level": 2,
                        "context_used": {"workflow": True}
                    }
                elif workflow_result.get("error"):
                    return {
                        "success": False,
                        "response": f"[CONFIDENCE: HIGH] [AUTONOMY: LEVEL 2]\n\n❌ Error: {workflow_result['error']}",
                        "autonomy_level": 2,
                        "context_used": {"workflow": True}
                    }

            # Without ! prefix - show preview for confirmation
            if workflow_result.get("requires_confirmation") or workflow_result.get("preview"):
                cache_key = f"pending_confirm:{self.user}:{channel_id}"
                frappe.cache().set_value(cache_key, query, expires_in_sec=300)
                frappe.logger().info(f"[Workflow] Stored pending command for confirm: {query}")
                return {
                    "success": True,
                    "response": f"[CONFIDENCE: HIGH] [AUTONOMY: LEVEL 2]\n\n{workflow_result.get('message') or workflow_result.get('preview', 'Ready to execute. Use ! to confirm.')}",
                    "autonomy_level": 2,
                    "context_used": {"workflow": True}
                }
            elif workflow_result.get("success"):
                return {
                    "success": True,
                    "response": f"[CONFIDENCE: HIGH] [AUTONOMY: LEVEL 2]\n\n{workflow_result.get('message', 'Operation completed.')}",
                    "autonomy_level": 2,
                    "context_used": {"workflow": True}
                }
            elif workflow_result.get("error"):
                return {
                    "success": False,
                    "response": f"[CONFIDENCE: HIGH] [AUTONOMY: LEVEL 2]\n\n❌ Error: {workflow_result['error']}",
                    "autonomy_level": 2,
                    "context_used": {"workflow": True}
                }

        # === FIX: Cache LLM-path commands requiring confirmation ===
        is_confirm = any(word in query_lower for word in ["confirm", "yes", "proceed", "do it", "execute", "si", "confirmar"])

        if query.startswith("!"):
            is_confirm = True
        elif suggested_autonomy >= 2 and not is_confirm:
            cache_key = f"pending_confirm:{self.user}:{channel_id}"
            existing = frappe.cache().get_value(cache_key)
            if not existing:
                frappe.cache().set_value(cache_key, query, expires_in_sec=300)
                frappe.logger().info(f"[LLM Path] Stored pending command for confirm (autonomy={suggested_autonomy}): {query}")

        # Build context
        morning_briefing = self.get_morning_briefing()
        erpnext_context = self.get_erpnext_context(query)
        relevant_memories = self.search_memories(query)

        memories_text = "\n".join([f"- {m['content']}" for m in relevant_memories])

        # Build messages
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": f"## Context\n{morning_briefing}\n\n## ERPNext Data\n{erpnext_context}\n\n## Relevant Memories\n{memories_text}"}
        ]

        # Add conversation history
        if conversation_history:
            messages.extend(conversation_history[-10:])

        # Add current query with autonomy context
        autonomy_warning = ""
        if query.startswith("!"):
            autonomy_warning = "\n\n✅ EXECUTE DIRECTLY - User has confirmed with ! prefix. Perform the action without asking for confirmation."
        elif suggested_autonomy >= 2:
            autonomy_warning = f"\n\n⚠️ This query suggests LEVEL {suggested_autonomy} autonomy. Please confirm before executing any changes. (Tip: Use `@ai !command` to skip confirmation)"

        messages.append({"role": "user", "content": query + autonomy_warning})

        # Call LLM
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.settings.get("max_tokens", 2000),
                temperature=0.3
            )

            answer = response.choices[0].message.content

            return {
                "success": True,
                "response": answer,
                "autonomy_level": suggested_autonomy,
                "context_used": {
                    "memories": len(relevant_memories),
                    "erpnext_data": bool(erpnext_context)
                }
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "response": f"[CONFIDENCE: UNCERTAIN]\n\nI encountered an error processing your request: {str(e)}"
            }


# ==================== API ENTRY POINTS ====================
@frappe.whitelist()
def process_message(message: str, conversation_history: str = None) -> Dict:
    """API endpoint for processing messages"""
    user = frappe.session.user
    agent = RaymondLucyAgent(user)

    history = json.loads(conversation_history) if conversation_history else []

    return agent.process_query(message, history)


@frappe.whitelist()
def handle_raven_message(doc, method):
    """Hook for Raven message integration - handles @ai and @bot_name mentions in any channel"""
    from bs4 import BeautifulSoup

    try:
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

        # ==================== PRE-PROCESSOR: Data Quality Scanner ====================
        # Run scanner FIRST for scan/validate commands - pre-flight validation
        # This bypasses routing complexity and ensures data quality checks run before operations
        if plain_text.lower().startswith("@ai"):
            query = plain_text[3:].strip()
            q_lower = query.lower()
            
            scanner_keywords = ["scan", "validate", "pre-flight", "preflight", "repair", "solve"]
            if any(kw in q_lower for kw in scanner_keywords):
                try:
                    from raven_ai_agent.skills.data_quality_scanner.skill import DataQualityScannerSkill
                    scanner = DataQualityScannerSkill()
                    scanner_result = scanner.handle(query, {"channel_id": doc.channel_id})
                    
                    if scanner_result and scanner_result.get("handled"):
                        response_text = scanner_result.get("response", "Scan complete.")
                        reply_doc = frappe.get_doc({
                            "doctype": "Raven Message",
                            "channel_id": doc.channel_id,
                            "text": response_text,
                            "message_type": "Text",
                            "is_bot_message": 1
                        })
                        reply_doc.insert(ignore_permissions=True)
                        return
                except Exception:
                    # Continue with normal routing if scanner fails
                    pass
        # ==================== END PRE-PROCESSOR ====================

        # Check for @ai trigger (now on plain text) — route to correct agent by intent
        if plain_text.lower().startswith("@ai"):
            # Detect intent to route to specialized agents
            q_lower = query.lower()

            # Phase 4: Analytics commands route to RaymondLucyAgent (default)
            analytics_keywords = [
                "dashboard", "tablero", "trend", "tendencia",
                "report daily", "report weekly", "report monthly",
                "reporte diario", "reporte semanal", "reporte mensual",
                "alerts status", "alerts check", "alerts configure",
                "alerta", "executive overview", "resumen ejecutivo",
                "financial snapshot", "quality metric", "kpi dashboard"
            ]
            is_analytics = any(kw in q_lower for kw in analytics_keywords)
            if is_analytics:
                bot_name = "sales_order_bot"  # Routes to RaymondLucyAgent which has AnalyticsMixin

            # Enhanced keyword lists for better distribution
            mfg_keywords = [
                "work order", "create wo", "submit wo", "manufacture",
                "transfer material", "check material", "mfg-wo", "wo plan",
                "create batch", "show work order", "list work order",
                "mis ordenes", "show wo", "mfg status", "mfg dashboard",
                "manufacturing status", "manufacturing dashboard",
                "finish work order", "complete work order",
                "material receipt", "material issue", "stock entry",
                "job card", "production plan", "bom creator",
                "quality check", "quality inspection", "qc pass", "qc fail"
            ]
            pay_keywords = [
                "payment", "outstanding", "unpaid", "reconcile",
                "acc-sinv", "acc-pay", "sinv-", "purchase invoice",
                "sales invoice", "payment entry", "make payment",
                "receive payment", "payment received"
            ]
            orch_keywords = [
                "pipeline status", "run full cycle", "run pipeline",
                "dry run", "validate so", "full cycle", "complete workflow"
            ]
            batch_keywords = [
                "batch create", "batch run", "batch status", "batch process",
                "lote crear", "lote ejecutar", "lote status"
            ]
            validator_keywords = [
                "diagnosis", "diagnose", "validate ", "audit pipeline",
                "check payment", "check pago", "pipeline health",
                "verify so", "verify sales order", "sync so", "fix so",
                "sync sales order", "fix sales order", "!sync", "!fix",
                "audit bom", "check bom", "validate bom",
                # Check data commands for quotations
                "check data ", "check data SAL-", "check data QUOT-",
                # Fix commands - route to task_validator for actual fixes
                "fix", "fix ", "fix SAL-", "fix QUOT-", "fix SO-",
                # Pipeline commands - route to task_validator
                "pipeline", "pipeline SAL-QTN-", "pipeline SAL-ORD-", "pipeline QUOT-",
                "pipeline "  # Must be last - catches "pipeline" alone
            ]

            # === SCANNER/DATA QUALITY commands - route to SkillRouter (before SO check) ===
            scanner_keywords = [
                "scan", "pre-flight", "preflight",
                "quality check", "check address", "check account", "check invoice",
                "verificar"
            ]
            
            # DEBUG: Log the query and matching
            frappe.logger().info(f"[AI Agent] Query: '{q_lower}' | Scanner keywords: {scanner_keywords}")
            
            if any(kw in q_lower for kw in scanner_keywords):
                frappe.logger().info(f"[AI Agent] MATCHED scanner keywords, bot_name=None")
                bot_name = None  # Will route to SkillRouter in else case below
            
            # === PRIORITY: Payment-linked commands (ACC-SINV, ACC-PAY) - BEFORE validator ===
            # This must come BEFORE validator_keywords to route payment commands to payment_bot
            if re.search(r'ACC-SINV-|ACC-PAY-|sinv-|acc-sinv|acc-pay', q_lower, re.IGNORECASE):
                bot_name = "payment_bot"
            
            # === PRIORITY: Validator keywords BEFORE SO pattern ===
            # "diagnose SAL-QTN-00752" contains "00752" matching SO-\d+, so check validator first
            if any(kw in q_lower for kw in validator_keywords):
                bot_name = "task_validator"
            # === PRIORITY: SO-linked commands always go to sales agent ===
            elif re.search(r'SO-\d+', q_lower, re.IGNORECASE) or re.search(r'from\s+SO', q_lower, re.IGNORECASE):
                # Exclude actual payment commands
                if not re.search(r'(?:reconcile|submit\s+ACC-PAY|ACC-PAY-\d+)', q_lower, re.IGNORECASE):
                    bot_name = "sales_order_follow_up"
                else:
                    # It's a payment command, continue to payment routing below
                    pass
            # === BATCH commands - route to BatchOrchestrator for generic batch processing ===
            elif q_lower.strip().startswith("batch "):
                bot_name = "batch_orchestrator"
            # === Batch commands via keywords ===
            elif any(kw in q_lower for kw in batch_keywords):
                bot_name = "batch_orchestrator"
            # === Legacy: Specific batch invoice/delivery commands go to sales agent ===
            elif "batch" in q_lower and ("invoice" in q_lower or "factura" in q_lower or "delivery" in q_lower):
                bot_name = "sales_order_follow_up"
            # Route by priority (more specific first) — skip if analytics already matched
            elif is_analytics:
                pass  # Already set to sales_order_bot → RaymondLucyAgent
            elif any(kw in q_lower for kw in validator_keywords):
                bot_name = "task_validator"
            elif any(kw in q_lower for kw in orch_keywords):
                bot_name = "workflow_orchestrator"
            elif any(kw in q_lower for kw in mfg_keywords):
                bot_name = "manufacturing_bot"
            elif any(kw in q_lower for kw in pay_keywords):
                bot_name = "payment_bot"
            else:
                bot_name = "sales_order_bot"  # Default bot

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

        # Check for @manufacturing or @mfg bot
        elif "manufacturing" in plain_text.lower() or "@mfg" in plain_text.lower():
            query = plain_text
            for tag in ["@manufacturing", "@Manufacturing", "@mfg", "@MFG"]:
                query = query.replace(tag, "")
            query = query.strip()
            if not query:
                query = "help"
            bot_name = "manufacturing_bot"

        # Check for @payment bot
        elif plain_text.lower().startswith("@payment"):
            query = plain_text
            for tag in ["@payment", "@Payment"]:
                query = query.replace(tag, "")
            query = query.strip()
            if not query:
                query = "help"
            bot_name = "payment_bot"

        # Check for @workflow or @orchestrator or @pipeline bot
        elif any(kw in plain_text.lower() for kw in ["@workflow", "@orchestrator", "@pipeline"]):
            query = plain_text
            for tag in ["@workflow", "@Workflow", "@orchestrator", "@Orchestrator", "@pipeline", "@Pipeline"]:
                query = query.replace(tag, "")
            query = query.strip()
            if not query:
                query = "help"
            bot_name = "workflow_orchestrator"

        if not query:
            return

        user = doc.owner
        frappe.logger().info(f"[AI Agent] Routing: {bot_name} | User: {user} | Query: {query[:50]}...")

        # Use ignore_permissions flag instead of switching user
        original_ignore = frappe.flags.ignore_permissions
        try:
            frappe.flags.ignore_permissions = True

            # Route to specialized agent based on bot_name
            if bot_name == "sales_order_follow_up":
                from raven_ai_agent.agents import SalesOrderFollowupAgent
                so_agent = SalesOrderFollowupAgent(user)
                response = so_agent.process_command(query)
                result = {"success": True, "response": response}
            elif bot_name == "rnd_bot":
                from raven_ai_agent.agents import RnDAgent
                rnd_agent = RnDAgent(user)
                response = rnd_agent.process_command(query)
                result = {"success": True, "response": response}
            elif bot_name == "executive":
                from raven_ai_agent.agents.executive_agent import ExecutiveAgent
                exec_agent = ExecutiveAgent(user)
                response = exec_agent.process_command(query)
                result = {"success": True, "response": response}
            elif bot_name == "iot":
                from raven_ai_agent.agents.iot_agent import IoTAgent
                iot_agent = IoTAgent(user)
                result = iot_agent.process_command(query)
            elif bot_name == "manufacturing_bot":
                from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
                mfg_agent = ManufacturingAgent(user)
                response = mfg_agent.process_command(query)
                result = {"success": True, "response": response}
            elif bot_name == "payment_bot":
                from raven_ai_agent.agents.payment_agent import PaymentAgent
                pay_agent = PaymentAgent(user)
                response = pay_agent.process_command(query)
                result = {"success": True, "response": response}
            elif bot_name == "workflow_orchestrator":
                from raven_ai_agent.agents.workflow_orchestrator import WorkflowOrchestrator
                wf_agent = WorkflowOrchestrator(user)
                response = wf_agent.process_command(query)
                result = {"success": True, "response": response}
            elif bot_name == "batch_orchestrator":
                from raven_ai_agent.agents.batch_orchestrator import BatchOrchestrator
                batcher = BatchOrchestrator(user)
                response = batcher.process_command(query)
                result = {"success": True, "response": response}
            elif bot_name == "task_validator":
                from raven_ai_agent.agents.task_validator import TaskValidator
                try:
                    validator = TaskValidator()
                    validator_result = validator.handle(query, {"channel_id": doc.channel_id} if doc else None)
                    frappe.logger().info(f"[AI Agent] TaskValidator result: {validator_result}")
                    if validator_result:
                        # Handle response, message, and error keys from task_validator
                        if validator_result.get("error"):
                            # Return error message properly
                            result = {"success": False, "response": f"Error: {validator_result.get('error')}"}
                        else:
                            response_text = validator_result.get("response") or validator_result.get("message") or "Validation complete"
                            result = {"success": True, "response": response_text}
                    else:
                        result = {"success": False, "response": "Could not process validator command. Try: `@ai diagnose SAL-QTN-XXXX`"}
                except Exception as e:
                    frappe.logger().error(f"[AI Agent] TaskValidator error: {e}")
                    result = {"success": False, "response": f"Error: {str(e)}"}
            else:
                # Try SkillRouter for other specialized skills
                try:
                    from raven_ai_agent.skills.router import SkillRouter
                    router = SkillRouter()
                    router_result = router.route(query)
                    if router_result and router_result.get("handled"):
                        result = {"success": True, "response": router_result.get("response", "Skill executed.")}
                    else:
                        agent = RaymondLucyAgent(user)
                        result = agent.process_query(query, channel_id=doc.channel_id)
                except Exception as e:
                    frappe.logger().error(f"[AI Agent] SkillRouter error: {e}")
                    agent = RaymondLucyAgent(user)
                    result = agent.process_query(query, channel_id=doc.channel_id)
        finally:
            frappe.flags.ignore_permissions = original_ignore

        frappe.logger().info(f"[AI Agent] Result: success={result.get('success')}")

        # Get bot for proper message sending
        bot = None
        if bot_name:
            try:
                bot = frappe.get_doc("Raven Bot", bot_name)
            except frappe.DoesNotExistError:
                frappe.logger().warning(f"[AI Agent] Bot {bot_name} not found")

        response_text = result.get("response") or result.get("message") or result.get("error") or "No response generated"
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
                "text": f"❌ Error: {str(e)}",
                "message_type": "Text",
                "is_bot_message": 1
            })
            error_doc.insert(ignore_permissions=True)
            frappe.db.commit()

            # Publish realtime event for error message too
            publish_message_created_event(error_doc, doc.channel_id)
        except Exception:
            pass
