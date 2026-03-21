"""
Intent Resolver - Natural Language to Command Resolution
Phase 7: LLM-based intent classification and entity extraction

This module converts natural language text into documented command formats
before passing to the existing command router.
"""

import frappe
import re
import json
import time
from typing import Optional, Dict, List, Tuple
from functools import lru_cache


# Command Catalog - maps intents to command templates
# Based on @ai help output and command_router.py patterns
COMMAND_CATALOG = {
    # Status & Diagnostics
    "status_check": [
        "diagnose {document_id}",
        "status {doc_type} {doc_id}",
        "workflow status {doc_type} {doc_id}",
        "track {doc_type} {doc_id}",
    ],
    "pipeline_diagnosis": [
        "diagnose {quotation_id}",
        "validate pipeline {quotation_id}",
        "check pipeline for {quotation_id}",
    ],
    
    # Sales Order Operations
    "create_sales_order": [
        "convert quotation {qtn_id} to sales order",
        "create sales order from {qtn_id}",
        "convert {qtn_id} to sales order",
    ],
    "submit_sales_order": [
        "!submit sales order {so_id}",
        "submit sales order {so_id}",
    ],
    "sales_order_to_work_order": [
        "create work order from {so_id}",
        "work order from {so_id}",
    ],
    "sales_order_to_delivery": [
        "delivery from {so_id}",
        "create delivery from {so_id}",
        "delivery note from {so_id}",
    ],
    "sales_order_to_invoice": [
        "invoice from {so_id}",
        "create invoice from {so_id}",
    ],
    
    # Quotation Operations
    "submit_quotation": [
        "submit quotation {qtn_id}",
        "!submit quotation {qtn_id}",
    ],
    "complete_workflow": [
        "complete workflow {qtn_id}",
        "complete {qtn_id} to invoice",
    ],
    
    # Delivery & Invoice
    "submit_delivery": [
        "!submit delivery {dn_id}",
        "submit delivery {dn_id}",
    ],
    "submit_invoice": [
        "!submit invoice {sinv_id}",
        "submit invoice {sinv_id}",
    ],
    
    # Work Order Operations
    "create_manufacturing_work_order": [
        "create work order from {so_id}",
        "work order for {so_id}",
    ],
    "stock_entry_work_order": [
        "stock entry for {wo_id}",
        "material transfer {wo_id}",
        "manufacture {wo_id}",
    ],
    
    # BOM Operations
    "create_bom": [
        "create bom for batch {batch_id}",
        "create bom for {batch_id}",
    ],
    "submit_bom": [
        "submit bom {bom_id}",
        "!submit bom {bom_id}",
    ],
    
    # Payment Operations
    "create_payment_entry": [
        "create payment for {sinv_id}",
        "payment for {sinv_id}",
        "pay invoice {sinv_id}",
    ],
    "get_unpaid_invoices": [
        "overdue invoices",
        "unpaid invoices",
        "show overdue",
    ],
    
    # Quality Management
    "quality_alert": [
        "create quality alert {item}",
        "quality alert for {item}",
    ],
    "quality_inspection": [
        "quality inspection {item}",
        "inspect {item}",
    ],
    
    # Analytics & Reporting
    "sales_dashboard": [
        "sales dashboard",
        "show sales report",
        "sales report",
    ],
    "analytics_query": [
        "show analytics {metric}",
        "analytics {metric}",
    ],
    
    # IoT / Sensors
    "sensor_status": [
        "sensor status {bot_id}",
        "sensor {bot_id}",
    ],
    "temperature_check": [
        "temperature {bot_id}",
        "check temperature {bot_id}",
        "temp {bot_id}",
    ],
    
    # Expense
    "create_expense": [
        "create expense {amount} {description}",
        "log expense {amount} {description}",
        "expense {amount} {description}",
    ],
    
    # Help
    "help": [
        "help",
        "show help",
        "what can you do",
    ],
    
    # Batch Operations
    "batch_migrate": [
        "batch migrate {qtn_list}",
        "migrate {qtn_list}",
    ],
}


# Regex patterns for direct command detection
DIRECT_COMMAND_PATTERNS = [
    # Document IDs
    r'SAL-QTN-\d+-\d+',        # Quotations
    r'SAL-ORD-\d+-\d+',        # Sales Orders
    r'SO-\d{3,5}',             # Short SO format
    r'SINV-\d+-\d+',           # Sales Invoices
    r'DN-\d+-\d+',             # Delivery Notes
    r'MFG-WO-\d+',             # Work Orders
    r'LOTE-\d+',               # Batch IDs
    r'BOM-[^\s]+',             # BOMs
    r'P-VTA-\d+',              # Production IDs
    
    # Direct command keywords
    r'^diagnose\s+',
    r'^status\s+',
    r'^track\s+',
    r'^help\s*$',
    r'^!submit\s+',
    r'^!cancel\s+',
    r'^!delete\s+',
    r'^convert\s+',
    r'^delivery\s+',
    r'^invoice\s+',
    r'^create\s+',
    r'^overdue\s+',
    r'^unpaid\s+',
]


class IntentResolver:
    """
    LLM-based intent resolver for natural language commands.
    
    Converts natural language queries like:
    "what is the status of my order for Calipso?"
    
    Into documented commands like:
    "diagnose SAL-ORD-2024-00754" or "status Sales Order SO-XXXXX"
    """
    
    def __init__(self):
        self.command_catalog = COMMAND_CATALOG
        self.confidence_threshold = 0.6
        self.use_llm_fallback = True
    
    def is_direct_command(self, raw_text: str) -> bool:
        """
        Fast pre-check: if text already matches a documented command pattern,
        return None to let the router handle it directly.
        """
        text_lower = raw_text.lower().strip()
        
        for pattern in DIRECT_COMMAND_PATTERNS:
            if re.search(pattern, raw_text, re.IGNORECASE):
                frappe.logger().info(f"[IntentResolver] Direct command pattern matched: {pattern}")
                return True
        
        # Check for @ai prefix (already processed)
        if text_lower.startswith("@ai "):
            return True
        
        return False
    
    def resolve_intent(self, raw_text: str) -> Optional[Dict]:
        """
        Main entry point: resolve natural language to documented command.
        
        Returns:
            Dict with keys: intent, entities, resolved_command, confidence
            OR None if should fall through to existing router
        """
        # Fast path: check for direct command patterns
        if self.is_direct_command(raw_text):
            frappe.logger().info(f"[IntentResolver] Direct command detected, skipping: {raw_text}")
            return None
        
        # Check cache first
        cache_key = f"intent_resolve:{raw_text.strip().lower()}"
        cached = frappe.cache().get_value(cache_key)
        if cached:
            frappe.logger().info(f"[IntentResolver] Cache hit: {raw_text}")
            return json.loads(cached) if isinstance(cached, str) else cached
        
        # Try LLM-based resolution
        try:
            result = self._resolve_via_llm(raw_text)
            
            # Cache the result
            if result:
                frappe.cache().set_value(cache_key, json.dumps(result), expires_in=3600)  # 1 hour
            
            return result
            
        except Exception as e:
            frappe.logger().error(f"[IntentResolver] LLM resolution failed: {e}")
            # Fall through to existing router on any error
            return None
    
    def _resolve_via_llm(self, raw_text: str) -> Optional[Dict]:
        """Use LLM to classify intent and extract entities"""
        
        # Build prompt with command catalog
        catalog_text = self._build_command_catalog_text()
        
        prompt = f"""You are an intent classifier for a voice assistant that maps natural language to documented commands.

AVAILABLE COMMANDS:
{catalog_text}

USER MESSAGE: "{raw_text}"

Your task:
1. Classify the intent (match to one of the available commands)
2. Extract entities (customer names, document IDs, item codes, amounts)
3. Map to a documented command format from the available commands

Return JSON with:
{{
    "intent": "intent_name or null",
    "entities": {{
        "customer_name": "extracted or null",
        "document_id": "extracted or null", 
        "doc_type": "Sales Order, Quotation, etc. or null",
        "item_code": "extracted or null",
        "amount": "extracted or null",
        "description": "extracted or null"
    }},
    "resolved_command": "the documented command string with entities filled in, or null",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation"
}}

Rules:
- If confidence < 0.6, set resolved_command to null
- Use exact document ID formats: SAL-QTN-XXXXXX, SAL-ORD-XXXXXX, SO-XXX, etc.
- Only use commands from the AVAILABLE COMMANDS list
- If user is just greeting or asking something not in commands, return intent=null, resolved_command=null, confidence=0.1

Return ONLY valid JSON, no additional text:"""

        # Call LLM
        try:
            llm_response = self._call_llm(prompt)
            
            # Parse response
            result = self._parse_llm_response(llm_response)
            
            # Log the resolution
            if result and result.get("resolved_command"):
                frappe.logger().info(
                    f"[IntentResolver] \"{raw_text}\" -> \"{result['resolved_command']}\" "
                    f"(conf={result.get('confidence', 0)}, intent={result.get('intent')})"
                )
            
            return result
            
        except Exception as e:
            frappe.logger().error(f"[IntentResolver] LLM call failed: {e}")
            raise
    
    def _build_command_catalog_text(self) -> str:
        """Build human-readable command catalog for prompt"""
        lines = []
        for intent, commands in self.command_catalog.items():
            lines.append(f"- {intent}: {', '.join(commands[:2])}")
        return "\n".join(lines)
    
    def _call_llm(self, prompt: str) -> str:
        """Call LLM endpoint - uses existing configuration"""
        
        # Try to get LLM settings from Frappe
        try:
            settings = frappe.get_doc("Raven AI Settings")
            provider = settings.get("default_provider", "openai")
            
            if provider == "openai":
                import openai
                api_key = settings.get_password("openai_api_key") if hasattr(settings, "get_password") else None
                if api_key:
                    openai.api_key = api_key
                    
                    response = openai.ChatCompletion.create(
                        model="gpt-3.5-turbo",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.1,
                        max_tokens=500,
                    )
                    return response.choices[0].message.content
                    
        except Exception as e:
            frappe.logger().warning(f"[IntentResolver] OpenAI call failed: {e}")
        
        # Fallback: simple rule-based resolution if LLM unavailable
        return self._fallback_resolution(prompt)
    
    def _fallback_resolution(self, prompt: str) -> str:
        """
        Fallback resolution when LLM is unavailable.
        Uses simple pattern matching.
        """
        # Extract patterns from prompt
        text_match = re.search(r'USER MESSAGE: "([^"]+)"', prompt)
        if not text_match:
            return '{"intent": null, "resolved_command": null, "confidence": 0.0}'
        
        text = text_match.group(1).lower()
        
        # Simple keyword-based intent detection
        intent = None
        entities = {}
        resolved_command = None
        confidence = 0.3
        
        # Status check patterns
        if any(word in text for word in ["status", "track", "how is", "what is the status"]):
            doc_id = self.extract_document_id(text)
            if doc_id:
                intent = "status_check"
                entities["document_id"] = doc_id
                resolved_command = f"diagnose {doc_id}"
                confidence = 0.7
        
        # Create sales order patterns
        elif any(word in text for word in ["create sales order", "convert quotation", "convert to sales order"]):
            qtn_id = self.extract_document_id(text, patterns=[r'SAL-QTN-\d+-\d+'])
            if qtn_id:
                intent = "create_sales_order"
                entities["document_id"] = qtn_id
                resolved_command = f"convert quotation {qtn_id} to sales order"
                confidence = 0.7
        
        # Work order patterns
        elif "work order" in text:
            so_id = self.extract_document_id(text, patterns=[r'SAL-ORD-\d+-\d+', r'SO-\d{3,5}'])
            if so_id:
                intent = "sales_order_to_work_order"
                entities["document_id"] = so_id
                resolved_command = f"create work order from {so_id}"
                confidence = 0.7
        
        # Delivery patterns
        elif any(word in text for word in ["delivery", "ship"]):
            so_id = self.extract_document_id(text, patterns=[r'SAL-ORD-\d+-\d+', r'SO-\d{3,5}'])
            if so_id:
                intent = "sales_order_to_delivery"
                entities["document_id"] = so_id
                resolved_command = f"delivery from {so_id}"
                confidence = 0.7
        
        # Invoice patterns
        elif any(word in text for word in ["invoice", "factura"]):
            so_id = self.extract_document_id(text, patterns=[r'SAL-ORD-\d+-\d+', r'SO-\d{3,5}'])
            if so_id:
                intent = "sales_order_to_invoice"
                entities["document_id"] = so_id
                resolved_command = f"invoice from {so_id}"
                confidence = 0.7
        
        # Help patterns
        elif any(word in text for word in ["help", "what can you do", "commands"]):
            intent = "help"
            resolved_command = "help"
            confidence = 0.9
        
        # Overdue patterns
        elif any(word in text for word in ["overdue", "unpaid", "pending payment"]):
            intent = "get_unpaid_invoices"
            resolved_command = "overdue invoices"
            confidence = 0.8
        
        return json.dumps({
            "intent": intent,
            "entities": entities,
            "resolved_command": resolved_command,
            "confidence": confidence,
            "reasoning": "Fallback rule-based resolution"
        })
    
    def _parse_llm_response(self, response: str) -> Optional[Dict]:
        """Parse JSON from LLM response"""
        try:
            # Extract JSON from response
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(0))
                
                # Validate result
                if not isinstance(result, dict):
                    return None
                
                # Apply confidence threshold
                if result.get("confidence", 0) < self.confidence_threshold:
                    result["resolved_command"] = None
                
                return result
                
        except (json.JSONDecodeError, AttributeError) as e:
            frappe.logger().error(f"[IntentResolver] Failed to parse LLM response: {e}")
        
        return None
    
    def extract_document_id(self, text: str, patterns: List[str] = None) -> Optional[str]:
        """
        Extract document IDs from text using regex patterns.
        """
        if patterns is None:
            patterns = [
                r'SAL-QTN-\d+-\d+',     # Quotations
                r'SAL-ORD-\d+-\d+',      # Sales Orders
                r'SO-\d{3,5}',           # Short SO format
                r'SINV-\d+-\d+',         # Sales Invoices
                r'DN-\d+-\d+',           # Delivery Notes
                r'MFG-WO-\d+',           # Work Orders
                r'LOTE-\d+',             # Batch IDs
                r'BOM-[^\s]+',           # BOMs
            ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0).upper()
        
        return None
    
    def extract_customer_name(self, text: str) -> Optional[str]:
        """
        Extract and fuzzy match customer names from text.
        Queries the Frappe database for matching customers.
        """
        # Common customer name patterns
        patterns = [
            r'for\s+([A-Za-z\s]+?)(?:\s+for|\s+order|\s+invoice|$)',
            r'customer\s+([A-Za-z\s]+?)(?:\s+order|\s+invoice|$)',
            r'company\s+([A-Za-z\s]+?)(?:\s+order|\s+invoice|$)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                customer_name = match.group(1).strip()
                
                # Try to find matching customer in DB
                try:
                    customers = frappe.db.get_all(
                        "Customer",
                        filters={"name": ["like", f"%{customer_name}%"]},
                        fields=["name", "customer_name"],
                        limit=5
                    )
                    
                    if customers:
                        # Return best match
                        return customers[0].name
                        
                except Exception as e:
                    frappe.logger().error(f"[IntentResolver] Customer lookup failed: {e}")
        
        return None
    
    def extract_item_code(self, text: str) -> Optional[str]:
        """
        Extract and fuzzy match item codes from text.
        Queries the Frappe database for matching items.
        """
        # Look for item-like patterns
        patterns = [
            r'item\s+([A-Za-z0-9-]+)',
            r'product\s+([A-Za-z0-9-]+)',
            r'([A-Z]{2,5}-\d{4,5})',  # Common item code format
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                item_code = match.group(1).strip()
                
                # Try to find matching item in DB
                try:
                    items = frappe.db.get_all(
                        "Item",
                        filters={"name": ["like", f"%{item_code}%"]},
                        fields=["name", "item_code"],
                        limit=5
                    )
                    
                    if items:
                        return items[0].name
                        
                except Exception as e:
                    frappe.logger().error(f"[IntentResolver] Item lookup failed: {e}")
        
        return None


@frappe.whitelist()
def resolve_intent_message(message: str) -> Optional[str]:
    """
    Whitelist wrapper for resolving intent from a message.
    Returns resolved command if confidence >= 0.7, else None.
    """
    if not message:
        return None
    
    # Strip @ai prefix if present
    if message.lower().startswith("@ai "):
        message = message[4:].strip()
    
    resolver = IntentResolver()
    result = resolver.resolve_intent(message)
    
    # Return resolved command if confidence is high enough
    if result and result.get("resolved_command"):
        confidence = result.get("confidence", 0)
        if confidence >= 0.7:
            # Log for debugging
            frappe.logger().info(
                f"[IntentResolver] Resolved: '{message}' -> '{result['resolved_command']}' "
                f"(conf={confidence})"
            )
            return result["resolved_command"]
    
    return None


def get_intent_resolver() -> IntentResolver:
    """Factory function to get IntentResolver instance"""
    return IntentResolver()
