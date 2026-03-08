"""
Raymond-Lucy AI Agent Core

Refactored: Split into handler modules under handlers/
Original monolith: 3104 lines -> Core: ~500 lines + 5 handler modules
"""
"""
Raymond-Lucy AI Agent Core
Anti-Hallucination + Persistent Memory + Autonomy Slider
"""
import frappe
import json
import re
import requests
from typing import Optional, Dict, List
from openai import OpenAI
from bs4 import BeautifulSoup

# Import channel utilities for realtime events
from raven_ai_agent.api.channel_utils import publish_message_created_event

# Import vector store for semantic search
try:
    from raven_ai_agent.utils.vector_store import VectorStore
    VECTOR_SEARCH_ENABLED = True
except ImportError:
    VECTOR_SEARCH_ENABLED = False

# Import workflow executor
try:
    from raven_ai_agent.api.workflows import WorkflowExecutor
    WORKFLOWS_ENABLED = True
except ImportError:
    WORKFLOWS_ENABLED = False


# Import handler mixins
from raven_ai_agent.api.handlers import (
    ManufacturingMixin,
    BOMMixin,
    WebSearchMixin,
    SalesMixin,
    QuotationMixin,
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

CAPABILITIES_LIST = """
## 🤖 AI Agent Capabilities

**Available Bots:**
| Bot | Purpose |
|-----|---------|
| `@ai` | General ERPNext operations, manufacturing, sales, purchasing |
| `@sales_order_follow_up` | Dedicated SO tracking and fulfillment |
| `@rnd_bot` | R&D/Formulation research, innovation tracking |
| `@bom_creator` | BOM Creator automation |

### 📊 ERPNext Data Access
- `@ai show my quotations` - View your quotations, sales orders, work orders
- `@ai show pending deliveries` - Delivery notes, stock levels, inventory
- `@ai best selling items` - Sales analytics and reports
- `@ai TDS resolution for [item]` - Tax and compliance info

### 🌐 Web Research
- `@ai search [topic]` - Web search for any topic
- `@ai find suppliers for [product]` - Find manufacturers/suppliers
- `@ai extract from [URL]` - Extract data from any website
- `@ai who are the players in [market]` - Market research

### 📝 Create ERPNext Records
- `@ai create supplier [name]` - Create basic supplier
- `@ai create supplier [name] with address` - Search web & create with address
- `@ai save this research` - Cache research to AI Memory

### 🔧 Workflows (Level 2-3)
- `@ai convert quotation [name] to sales order` - Document conversion
- `@ai create work order for [item]` - Manufacturing workflows
- `!command` - Force execute without confirmation

### 🏭 Manufacturing SOP (Work Order → Finished Goods)

**Workflow:** Create WO → Submit → Issue Materials → Job Cards → Complete → FG Entry

**Work Order Management:**
- `@ai show work orders` - List active work orders
- `@ai create work order for [item] qty [n]` - Create new work order
- `@ai submit work order [WO]` - Submit/start work order
- `@ai material status for [WO]` - Check component availability
- `@ai reserve stock for [WO]` - Reserve materials for work order

**Production Execution:**
- `@ai issue materials for [WO]` - Transfer materials to WIP warehouse
- `@ai show job cards for [WO]` - List operations (linked to Project Tasks)
- `@ai update progress for [WO] qty [n]` - Report production progress
- `@ai finish work order [WO]` - Complete production & receive FG

**Quality & Costing:**
- `@ai quality check` - Show recent Quality Inspections
- `@ai show BOM cost report` - Compare estimated vs actual costs
- `@ai troubleshoot` - Manufacturing troubleshooting guide

**Stock Entry Management:**
- `@ai material receipt [ITEM] qty [n] price $[x]` - Create Material Receipt with price
- `@ai convert [STE] to material receipt` - Convert draft to Material Receipt
- `@ai verify stock entries` - Check submitted vs draft entries
- `@ai check stock ledger` - Show recent stock ledger entries
- `@ai list batches` - Show recently created batches

**Project Task ↔ BOM Operation Mapping:**
Job Cards auto-generated from BOM Operations align with Project Template tasks:
- TASK-00008: Recepción → TASK-00010: Molienda → TASK-00011: Prensado
- TASK-00012: Decolorado → TASK-00013: Filtrado → TASK-00023: Secado Spray

### 🔄 Sales-to-Purchase Cycle SOP
- `@ai show opportunities` - List sales opportunities
- `@ai create opportunity for [customer]` - Create new sales opportunity
- `@ai check inventory for [SO]` - Check item availability for Sales Order
- `@ai create material request for [SO]` - Create Material Request from SO
- `@ai show material requests` - List pending material requests
- `@ai create rfq from [MR]` - Create Request for Quotation
- `@ai show rfqs` - List RFQs and their status
- `@ai show supplier quotations` - List supplier quotations
- `@ai create po from [SQ]` - Create Purchase Order from Supplier Quotation
- `@ai receive goods for [PO]` - Create Purchase Receipt
- `@ai create purchase invoice for [PO]` - Bill against Purchase Order
- `@ai create delivery note for [SO]` - Ship items to customer
- `@ai create sales invoice for [SO/DN]` - Invoice the customer

### 📦 Sales Order Follow-up Bot
Use `@sales_order_follow_up` for dedicated SO tracking:
- `@sales_order_follow_up pending` - List all pending Sales Orders
- `@sales_order_follow_up status [SO]` - Detailed SO status
- `@sales_order_follow_up check inventory [SO]` - Check stock availability
- `@sales_order_follow_up next steps [SO]` - Recommended actions
- `@sales_order_follow_up track [SO]` - Full purchase cycle tracking

### 📋 BOM Management
- `@ai show bom BOM-XXXX` - View all items, operations, costs
- `@ai !cancel bom BOM-XXXX` - Cancel submitted BOM
- `@ai !revert bom BOM-XXXX to draft` - Reset cancelled BOM to draft
- `@ai check bom for [item]` - Check BOM label status
- `@ai fix bom for [item]` - Auto-fix missing labels
- `@ai force fix bom BOM-XXX label LBLXXX` - Force SQL insert

### 🏗️ BOM Creator
- `@ai show bom [NAME]` - View BOM or BOM Creator details
- `@ai !submit bom BOM-XXXX` - Submit BOM Creator to generate BOMs
- `@ai validate bom BOM-XXXX` - Validate BOM Creator before submission
- `@ai create bom from tds [TDS-NAME]` - Create BOM Creator from TDS
- `@ai create bom for batch LOTE-XXXX` - Create BOM for a Batch AMB

### 📄 Document Actions
- `@ai !submit Sales Order SO-XXXX` - Submit sales order
- `@ai !submit Work Order MFG-WO-XXXX` - Submit work order
- `@ai unlink sales order from MFG-WO-XXXX` - Remove SO link from WO
- `@ai !fix quotation SAL-QTN-XXXX` - Fix cancelled quotation (revert to draft)
- `@ai !fix quotation from SAL-QTN-XXXX to SAL-QTN-YYYY` - Batch fix range
- `@ai !update quotation SAL-QTN-XXXX item ITEM-CODE` - Update quotation item & TDS

### ℹ️ Help
- `@ai help` or `@ai capabilities` - Show this list
- `@ai what can you do` - Show capabilities

Type your question and I'll help!
"""




class RaymondLucyAgent(
    ManufacturingMixin,
    BOMMixin,
    WebSearchMixin,
    SalesMixin,
    QuotationMixin,
):
    """
    Raymond-Lucy AI Agent - ERPNext AI Assistant
    Anti-Hallucination + Persistent Memory + Autonomy Slider
    
    Composed from handler mixins for modularity:
    - ManufacturingMixin: Manufacturing SOP + Stock Entry (606 lines)
    - BOMMixin: BOM commands + label fixer + cancel (267 lines)
    - WebSearchMixin: Direct web search (53 lines)
    - SalesMixin: Sales-to-Purchase cycle (477 lines)
    - QuotationMixin: Quotation fix + update + TDS (415 lines)
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
    
    def get_morning_briefing(self) -> str:
        """Lucy Protocol: Load context at session start"""
        # Get user's critical memories
        memories = frappe.get_list(
            "AI Memory",
            filters={"user": self.user, "importance": ["in", ["Critical", "High"]]},
            fields=["content", "importance", "source"],
            order_by="creation desc",
            limit=10
        )
        
        # Get latest summary
        summaries = frappe.get_list(
            "AI Memory",
            filters={"user": self.user, "memory_type": "Summary"},
            fields=["content"],
            order_by="creation desc",
            limit=1
        )
        
        briefing = "## Morning Briefing\n\n"
        
        if summaries:
            briefing += f"**Last Session Summary:**\n{summaries[0].content}\n\n"
        
        if memories:
            briefing += "**Key Facts:**\n"
            for m in memories:
                briefing += f"- [{m.importance}] {m.content}\n"
        
        return briefing
    
    def search_memories(self, query: str, limit: int = 5) -> List[Dict]:
        """RAG: Search relevant memories using vector similarity"""
        if VECTOR_SEARCH_ENABLED:
            try:
                vector_store = VectorStore()
                return vector_store.search_similar(
                    user=self.user,
                    query=query,
                    limit=limit,
                    similarity_threshold=self.settings.get("confidence_threshold", 0.7)
                )
            except Exception:
                pass  # Fallback to keyword search
        
        # Fallback: Simple keyword search
        memories = frappe.get_list(
            "AI Memory",
            filters={
                "user": self.user,
                "content": ["like", f"%{query}%"]
            },
            fields=["content", "importance", "source", "creation"],
            order_by="creation desc",
            limit=limit
        )
        return memories
    
    def tattoo_fact(self, content: str, importance: str = "Normal", source: str = None):
        """Memento Protocol: Store important fact with embedding"""
        if VECTOR_SEARCH_ENABLED:
            try:
                vector_store = VectorStore()
                return vector_store.store_memory_with_embedding(
                    user=self.user,
                    content=content,
                    importance=importance,
                    source=source
                )
            except Exception:
                pass  # Fallback to basic storage
        
        # Fallback: Store without embedding
        doc = frappe.get_doc({
            "doctype": "AI Memory",
            "user": self.user,
            "content": content,
            "importance": importance,
            "memory_type": "Fact",
            "source": source or "Conversation"
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc.name
    
    # Doctype keyword mappings for dynamic detection
    DOCTYPE_KEYWORDS = {
        "Sales Invoice": ["invoice", "factura", "billing", "invoiced"],
        "Sales Order": ["sales order", "orden de venta", "so-", "pedido"],
        "Purchase Order": ["purchase order", "orden de compra", "po-"],
        "Purchase Invoice": ["purchase invoice", "factura de compra"],
        "Quotation": ["quotation", "quote", "cotización", "cotizacion"],
        "Customer": ["customer", "client", "cliente"],
        "Supplier": ["supplier", "vendor", "proveedor"],
        "Item": ["item", "product", "artículo", "articulo", "producto"],
        "Stock Entry": ["stock entry", "stock", "inventario", "inventory"],
        "Delivery Note": ["delivery", "shipping", "entrega", "envío"],
        "Purchase Receipt": ["purchase receipt", "receipt", "recepción"],
        "Work Order": ["work order", "manufacturing", "production", "producción"],
        "BOM": ["bom", "bill of material", "lista de materiales"],
        "Quality Inspection": ["quality", "inspection", "qc", "calidad", "inspección"],
        "Material Request": ["material request", "requisición", "requisicion"],
        "Lead": ["lead", "prospecto"],
        "Opportunity": ["opportunity", "oportunidad"],
        "Address": ["address", "dirección", "direccion"],
        "Contact": ["contact", "contacto"],
        "Employee": ["employee", "empleado"],
        "Warehouse": ["warehouse", "almacén", "almacen"],
        "Batch": ["batch", "lote"],
        "Serial No": ["serial", "serie"],
        "Payment Entry": ["payment", "pago"],
        "Journal Entry": ["journal", "asiento", "diario"],
    }
    
    def detect_doctype_from_query(self, query: str) -> List[str]:
        """Detect which doctypes the user is asking about"""
        query_lower = query.lower()
        detected = []
        for doctype, keywords in self.DOCTYPE_KEYWORDS.items():
            if any(kw in query_lower for kw in keywords):
                detected.append(doctype)
        return detected
    
    def query_doctype_with_permissions(self, doctype: str, query: str, limit: int = 10) -> List[Dict]:
        """Query a doctype if user has permissions"""
        try:
            # Check if user has read permission
            if not frappe.has_permission(doctype, "read"):
                return []
            
            # Get standard fields for the doctype
            meta = frappe.get_meta(doctype)
            fields = ["name"]
            
            # Add common useful fields if they exist
            common_fields = ["customer", "supplier", "grand_total", "total", "status", 
                           "transaction_date", "posting_date", "modified", "creation",
                           "item_code", "item_name", "customer_name", "party_name",
                           "territory", "company", "owner"]
            for field in common_fields:
                if meta.has_field(field):
                    fields.append(field)
            
            # Build filters based on query context
            filters = {}
            
            # Check for specific document name patterns in query
            query_upper = query.upper()
            name_patterns = re.findall(r'[A-Z]{2,4}[-\s]?\d{4,}[-\w]*', query_upper)
            if name_patterns:
                filters["name"] = ["like", f"%{name_patterns[0]}%"]
            
            # Query the doctype
            results = frappe.get_list(
                doctype,
                filters=filters if filters else {"docstatus": ["<", 2]},
                fields=list(set(fields)),
                order_by="modified desc",
                limit=limit
            )
            
            # Add links to results
            site_name = frappe.local.site
            doctype_slug = doctype.lower().replace(" ", "-")
            for r in results:
                r["link"] = f"https://{site_name}/app/{doctype_slug}/{r['name']}"
                r["_doctype"] = doctype
            
            return results
        except Exception as e:
            frappe.logger().error(f"Error querying {doctype}: {str(e)}")
            return []
    
    def get_available_doctypes(self) -> List[str]:
        """Get list of doctypes user has permission to access"""
        available = []
        for doctype in self.DOCTYPE_KEYWORDS.keys():
            try:
                if frappe.has_permission(doctype, "read"):
                    available.append(doctype)
            except:
                pass
        return available
    
    def duckduckgo_search(self, query: str, max_results: int = 5) -> str:
        """Search the web using DuckDuckGo (no API key required)"""
        try:
            # Use DuckDuckGo HTML search
            search_url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}"
            response = requests.get(search_url, timeout=10, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            
            if response.status_code != 200:
                return f"Search failed: HTTP {response.status_code}"
            
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            
            # Parse DuckDuckGo HTML results
            for idx, result in enumerate(soup.find_all('div', class_='result')[:max_results], 1):
                title_tag = result.find('a', class_='result__a')
                snippet_tag = result.find('a', class_='result__snippet')
                
                if title_tag:
                    title = title_tag.get_text(strip=True)
                    raw_link = title_tag.get('href', '')
                    # Extract actual URL from DuckDuckGo redirect
                    if 'uddg=' in raw_link:
                        try:
                            from urllib.parse import unquote, parse_qs, urlparse
                            parsed = urlparse(raw_link)
                            params = parse_qs(parsed.query)
                            link = unquote(params.get('uddg', [raw_link])[0])
                        except:
                            link = raw_link
                    else:
                        link = raw_link
                    snippet = snippet_tag.get_text(strip=True) if snippet_tag else ''
                    results.append(f"**{idx}. {title}**\n🔗 {link}\n📝 {snippet}")
            
            if results:
                return "\n\n".join(results)
            else:
                return f"No search results found for: {query}"
                
        except Exception as e:
            frappe.logger().error(f"[AI Agent] DuckDuckGo search error: {str(e)}")
            return f"Search error: {str(e)}"
    
    def search_web(self, query: str, url: str = None) -> str:
        """Search the web or extract info from a specific URL"""
        try:
            if url:
                # Fetch specific URL with redirects
                response = requests.get(url, timeout=15, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5"
                }, allow_redirects=True)
                
                frappe.logger().info(f"[AI Agent] Web request to {url}: status={response.status_code}")
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Extract text content
                    for script in soup(["script", "style", "nav", "footer", "header"]):
                        script.decompose()
                    
                    extracted_data = []
                    
                    # Extract tables (for supplier lists, data tables)
                    tables = soup.find_all('table')
                    for table in tables[:3]:  # Max 3 tables
                        rows = table.find_all('tr')
                        table_text = []
                        for row in rows[:20]:  # Max 20 rows per table
                            cells = row.find_all(['td', 'th'])
                            row_text = ' | '.join(cell.get_text(strip=True) for cell in cells)
                            if row_text.strip():
                                table_text.append(row_text)
                        if table_text:
                            extracted_data.append("TABLE:\n" + "\n".join(table_text))
                    
                    # Extract lists (ul/ol) with company/supplier info
                    for lst in soup.find_all(['ul', 'ol'])[:5]:
                        items = lst.find_all('li')[:15]
                        list_items = [li.get_text(strip=True) for li in items if li.get_text(strip=True)]
                        if list_items and any(len(item) > 10 for item in list_items):
                            extracted_data.append("LIST:\n" + "\n".join(list_items))
                    
                    # Look for address/contact content
                    for tag in soup.find_all(['address', 'div', 'p', 'span']):
                        text = tag.get_text(strip=True)
                        if any(kw in text.lower() for kw in ['address', 'street', 'via', 'piazza', 'italy', 'italia', 'contact', 'location', 'supplier', 'manufacturer', 'company']):
                            if text not in extracted_data and len(text) > 20:
                                extracted_data.append(text)
                    
                    if extracted_data:
                        return f"Extracted from {url}:\n" + "\n\n".join(extracted_data[:15])
                    
                    # Fallback to general text
                    text = soup.get_text(separator=' ', strip=True)
                    return f"Content from {url}:\n{text[:4000]}"
                else:
                    return f"Could not fetch {url}: HTTP {response.status_code}"
            else:
                # Perform DuckDuckGo search for general queries
                return self.duckduckgo_search(query)
        except requests.exceptions.Timeout:
            return f"Web request timed out for {url}"
        except requests.exceptions.RequestException as e:
            return f"Web request failed for {url}: {str(e)}"
        except Exception as e:
            frappe.logger().error(f"[AI Agent] Web search error: {str(e)}")
            return f"Web search error: {str(e)}"
    
    def get_erpnext_context(self, query: str) -> str:
        """Raymond Protocol: Get verified ERPNext data based on user permissions"""
        context = []
        query_lower = query.lower()
        
        # Check for URL in query - fetch external website data
        url_match = re.search(r'https?://[^\s<>"\']+', query)
        if url_match:
            url = url_match.group(0).rstrip('.,;:')  # Clean trailing punctuation
            frappe.logger().info(f"[AI Agent] Fetching URL: {url}")
            web_content = self.search_web(query, url)
            if web_content and not web_content.startswith("Web search error"):
                context.insert(0, f"⭐ EXTERNAL WEB DATA (from {url}):\n{web_content}")
                frappe.logger().info(f"[AI Agent] Web content fetched: {len(web_content)} chars")
        
        # Check for web search intent (no URL but wants external info)
        search_keywords = ["search", "buscar", "find on web", "google", "look up", "search for", "search web", "find"]
        external_entities = ["barentz", "legosan", "website", "company info", "address", "contact", "ubicacion", "direccion", "indirizzo"]
        
        # Market research / external knowledge patterns
        market_keywords = ["market", "mercado", "players", "competitors", "suppliers", "manufacturers", 
                          "companies", "industry", "trend", "price", "pricing", "region", "country"]
        question_patterns = ["who are", "what are", "which", "list of", "tell me about", "information about",
                            "quienes son", "cuales son", "dime sobre"]
        
        # Check if query asks about external market/industry data
        is_market_question = (
            any(mk in query_lower for mk in market_keywords) and
            any(qp in query_lower for qp in question_patterns)
        )
        
        needs_web_search = (
            any(kw in query_lower for kw in search_keywords) or
            (any(ent in query_lower for ent in external_entities) and not url_match) or
            is_market_question
        )
        
        if needs_web_search and not url_match:
            # Extract search terms - remove common words
            search_terms = query_lower
            for word in ["@ai", "search", "find", "buscar", "look up", "web", "on", "for", "the", "a", "an"]:
                search_terms = re.sub(r'\b' + re.escape(word) + r'\b', ' ', search_terms)
            search_terms = " ".join(search_terms.split())  # Clean whitespace
            
            if len(search_terms) > 3:
                frappe.logger().info(f"[AI Agent] Web search for: {search_terms}")
                search_results = self.duckduckgo_search(search_terms)
                if search_results and "No search results" not in search_results:
                    context.insert(0, f"⭐ WEB SEARCH RESULTS:\n{search_results}")
        
        # Dynamic doctype detection - query any relevant doctypes user has permission to
        detected_doctypes = self.detect_doctype_from_query(query)
        for doctype in detected_doctypes:
            results = self.query_doctype_with_permissions(doctype, query)
            if results:
                context.append(f"{doctype} Data: {json.dumps(results, default=str)}")
        
        # Also run specific keyword-based queries for backward compatibility
        
        if any(word in query_lower for word in ["invoice", "sales", "revenue"]):
            invoices = frappe.get_list(
                "Sales Invoice",
                filters={"docstatus": 1},
                fields=["name", "customer", "grand_total", "posting_date"],
                order_by="posting_date desc",
                limit=5
            )
            if invoices:
                context.append(f"Recent Sales Invoices: {json.dumps(invoices, default=str)}")
        
        if any(word in query_lower for word in ["customer", "client"]):
            customers = frappe.get_list(
                "Customer",
                fields=["name", "customer_name", "territory"],
                limit=10
            )
            if customers:
                context.append(f"Customers: {json.dumps(customers, default=str)}")
        
        if any(word in query_lower for word in ["item", "product", "stock"]):
            items = frappe.get_list(
                "Item",
                fields=["name", "item_name", "stock_uom"],
                limit=10
            )
            if items:
                context.append(f"Items: {json.dumps(items, default=str)}")
        
        if any(word in query_lower for word in ["order", "purchase"]):
            orders = frappe.get_list(
                "Purchase Order",
                filters={"docstatus": ["<", 2]},
                fields=["name", "supplier", "grand_total", "status"],
                order_by="creation desc",
                limit=5
            )
            if orders:
                context.append(f"Purchase Orders: {json.dumps(orders, default=str)}")
        
        if any(word in query_lower for word in ["quotation", "quote", "cotización", "cotizacion"]):
            quotations = frappe.get_list(
                "Quotation",
                filters={"docstatus": ["<", 2]},
                fields=["name", "party_name", "grand_total", "status", "transaction_date", "valid_till"],
                order_by="creation desc",
                limit=10
            )
            if quotations:
                site_name = frappe.local.site
                for q in quotations:
                    q["link"] = f"https://{site_name}/app/quotation/{q['name']}"
                context.append(f"Quotations: {json.dumps(quotations, default=str)}")
        
        if any(word in query_lower for word in ["sales order", "orden de venta"]):
            sales_orders = frappe.get_list(
                "Sales Order",
                filters={"docstatus": ["<", 2]},
                fields=["name", "customer", "grand_total", "status", "transaction_date"],
                order_by="creation desc",
                limit=10
            )
            if sales_orders:
                site_name = frappe.local.site
                for so in sales_orders:
                    so["link"] = f"https://{site_name}/app/sales-order/{so['name']}"
                context.append(f"Sales Orders: {json.dumps(sales_orders, default=str)}")
        
        if any(word in query_lower for word in ["work order", "manufacturing", "production"]):
            work_orders = frappe.get_list(
                "Work Order",
                filters={"docstatus": ["<", 2]},
                fields=["name", "production_item", "qty", "status", "sales_order"],
                order_by="creation desc",
                limit=10
            )
            if work_orders:
                site_name = frappe.local.site
                for wo in work_orders:
                    wo["link"] = f"https://{site_name}/app/work-order/{wo['name']}"
                context.append(f"Work Orders: {json.dumps(work_orders, default=str)}")
        
        if any(word in query_lower for word in ["delivery", "shipping", "shipment"]):
            delivery_notes = frappe.get_list(
                "Delivery Note",
                filters={"docstatus": ["<", 2]},
                fields=["name", "customer", "grand_total", "status", "posting_date"],
                order_by="creation desc",
                limit=10
            )
            if delivery_notes:
                site_name = frappe.local.site
                for dn in delivery_notes:
                    dn["link"] = f"https://{site_name}/app/delivery-note/{dn['name']}"
                context.append(f"Delivery Notes: {json.dumps(delivery_notes, default=str)}")
        
        # Quality Inspection
        if any(word in query_lower for word in ["quality", "inspection", "qc", "inspeccion", "inspección", "calidad"]):
            inspections = frappe.get_list(
                "Quality Inspection",
                filters={"docstatus": ["<", 2]},
                fields=["name", "inspection_type", "reference_type", "reference_name", "status", "modified"],
                order_by="modified desc",
                limit=10
            )
            if inspections:
                site_name = frappe.local.site
                for qi in inspections:
                    qi["link"] = f"https://{site_name}/app/quality-inspection/{qi['name']}"
                context.append(f"Quality Inspections: {json.dumps(inspections, default=str)}")
            else:
                context.append("Quality Inspections: No records found")
        
        # TDS / Tax related to Sales Orders
        if any(word in query_lower for word in ["tds", "tax", "impuesto"]):
            # Get recent sales orders that might need TDS resolution
            sales_orders = frappe.get_list(
                "Sales Order",
                filters={"docstatus": ["<", 2]},
                fields=["name", "customer", "grand_total", "status", "taxes_and_charges"],
                order_by="creation desc",
                limit=10
            )
            if sales_orders:
                site_name = frappe.local.site
                for so in sales_orders:
                    so["link"] = f"https://{site_name}/app/sales-order/{so['name']}"
                context.append(f"Sales Orders (for TDS): {json.dumps(sales_orders, default=str)}")
        
        # Best selling / most sold items
        if any(word in query_lower for word in ["best sell", "most sold", "top sell", "vendido", "más vendido", "popular"]):
            try:
                top_items = frappe.db.sql("""
                    SELECT soi.item_code, soi.item_name, SUM(soi.qty) as total_qty, SUM(soi.amount) as total_amount
                    FROM `tabSales Order Item` soi
                    JOIN `tabSales Order` so ON soi.parent = so.name
                    WHERE so.docstatus = 1
                    GROUP BY soi.item_code, soi.item_name
                    ORDER BY total_qty DESC
                    LIMIT 10
                """, as_dict=True)
                if top_items:
                    context.append(f"Best Selling Items: {json.dumps(top_items, default=str)}")
            except Exception as e:
                context.append(f"Could not fetch best selling items: {str(e)}")
        
        # Customer-specific sales report
        customer_match = None
        for word in ["barentz", "legosan", "lorand"]:  # Add common customer names
            if word in query_lower:
                customer_match = word
                break
        
        if customer_match or any(word in query_lower for word in ["report", "reporte", "sales for"]):
            # Try to extract customer name from query
            if customer_match:
                customers = frappe.get_list(
                    "Customer",
                    filters={"name": ["like", f"%{customer_match}%"]},
                    fields=["name", "customer_name"],
                    limit=1
                )
                if customers:
                    customer_name = customers[0]["name"]
                    sales_data = frappe.get_list(
                        "Sales Order",
                        filters={"customer": customer_name, "docstatus": 1},
                        fields=["name", "grand_total", "transaction_date", "status"],
                        order_by="transaction_date desc",
                        limit=20
                    )
                    if sales_data:
                        site_name = frappe.local.site
                        for s in sales_data:
                            s["link"] = f"https://{site_name}/app/sales-order/{s['name']}"
                        context.append(f"Sales for {customer_name}: {json.dumps(sales_data, default=str)}")
        
        return "\n".join(context) if context else "No specific ERPNext data found for this query."
    
    def determine_autonomy(self, query: str) -> int:
        """Karpathy Protocol: Determine appropriate autonomy level"""
        query_lower = query.lower()
        
        # Level 3 keywords (dangerous operations)
        if any(word in query_lower for word in ["delete", "cancel", "submit", "create invoice", "payment"]):
            return 3
        
        # Level 2 keywords (modifications/workflow)
        if any(word in query_lower for word in ["update", "change", "modify", "set", "add", "convert", "create", "confirm"]):
            return 2
        
        # Default to Level 1 (read-only)
        return 1
    
    def execute_workflow_command(self, query: str, channel_id: str = "") -> Optional[Dict]:
        """Parse and execute workflow commands"""
        frappe.logger().info(f"[Workflow] Checking query: {query}, WORKFLOWS_ENABLED: {WORKFLOWS_ENABLED}")
        
        if not WORKFLOWS_ENABLED:
            frappe.logger().info("[Workflow] Workflows disabled")
            return None
        
        query_lower = query.lower()
        executor = WorkflowExecutor(self.user)
        
        # ---- Confirmation state management (Redis-backed) ----
        # When a preview is shown, we store the original command.
        # When user says "confirm", we replay the stored command with is_confirm=True.
        cache_key = f"pending_confirm:{self.user}:{channel_id}"
        
        is_confirm = any(word in query_lower for word in ["confirm", "yes", "proceed", "do it", "execute"])
        
        # If user said "confirm" and we have a pending command, replay it
        if is_confirm and query_lower.strip() in ["confirm", "yes", "proceed", "do it", "execute", "si", "confirmar"]:
            pending_cmd = frappe.cache().get_value(cache_key)
            if pending_cmd:
                frappe.cache().delete_value(cache_key)
                frappe.logger().info(f"[Workflow] Replaying pending command: {pending_cmd}")
                query = pending_cmd
                query_lower = query.lower()
                # is_confirm stays True
        
        # Force mode with ! prefix (like sudo)
        is_force = query.startswith("!")
        if is_force:
            is_confirm = True
            query = query.lstrip("!").strip()
            query_lower = query.lower()
        
        # Auto-confirm for privileged users ONLY on explicit confirm words,
        # NOT on initial commands. Without !, always show preview first.
        # This lets privileged users do:
        #   "invoice from SO-XXX"  → preview (dry run)
        #   "!invoice from SO-XXX" → execute immediately
        #   "confirm"              → execute (after preview)
        if not is_force:
            privileged_roles = ["Sales Manager", "Manufacturing Manager", "Stock Manager", "Accounts Manager", "System Manager"]
            user_roles = frappe.get_roles(self.user)
            if any(role in user_roles for role in privileged_roles):
                # Only auto-confirm if user said an explicit confirm word
                # Don't auto-confirm the initial command
                pass  # is_confirm stays as-is from keyword check above
        
        # Quotation patterns
        qtn_match = re.search(r'(SAL-QTN-\d+-\d+)', query, re.IGNORECASE)
        frappe.logger().info(f"[Workflow] qtn_match: {qtn_match}, 'sales order' in query: {'sales order' in query_lower}")
        
        # Dry-run mode
        is_dry_run = "--dry-run" in query_lower or "dry run" in query_lower
        if is_dry_run:
            executor.dry_run = True
        
        # Complete workflow: Quotation → Invoice
        if qtn_match and "complete" in query_lower and ("workflow" in query_lower or "invoice" in query_lower):
            from raven_ai_agent.api.workflows import complete_workflow_to_invoice
            return complete_workflow_to_invoice(qtn_match.group(1).upper(), dry_run=is_dry_run)
        
        # Batch migration: multiple quotations
        batch_match = re.findall(r'(SAL-QTN-\d+-\d+)', query, re.IGNORECASE)
        if len(batch_match) > 1 and ("batch" in query_lower or "migrate" in query_lower):
            return executor.batch_migrate_quotations([q.upper() for q in batch_match], dry_run=is_dry_run)
        
        # Submit quotation
        if qtn_match and "submit" in query_lower and "quotation" in query_lower:
            frappe.logger().info(f"[Workflow] Submitting quotation {qtn_match.group(1)}, confirm={is_confirm}")
            return executor.submit_quotation(qtn_match.group(1).upper(), confirm=is_confirm)
        
        # Quotation to Sales Order
        if qtn_match and "sales order" in query_lower:
            frappe.logger().info(f"[Workflow] Creating SO from {qtn_match.group(1)}, confirm={is_confirm}")
            return executor.create_sales_order_from_quotation(qtn_match.group(1).upper(), confirm=is_confirm)
        
        # Sales Order patterns - supports SAL-ORD-YYYY-NNNNN and SO-XXXXX-NAME formats
        so_match = re.search(r'(SAL-ORD-\d+-\d+|SO-[\w\-]+(?:\s+(?!from\b|to\b|pipeline\b|status\b|check\b|audit\b|validate\b|diagnose\b|bom\b|qty\b|quantity\b|item\b|warehouse\b|wh\b)[\w\.]+)*)', query, re.IGNORECASE)
        
        # Submit Sales Order
        if so_match and "submit" in query_lower and "sales order" in query_lower:
            return executor.submit_sales_order(so_match.group(1).upper(), confirm=is_confirm)
        
        # Sales Order to Work Order
        if so_match and "work order" in query_lower:
            return executor.create_work_orders_from_sales_order(so_match.group(1).upper(), confirm=is_confirm)
        
        # Stock Entry for Work Order
        wo_match = re.search(r'(MFG-WO-\d+|LOTE-\d+|P-VTA-\d+|WO-[^\s]+)', query, re.IGNORECASE)
        if wo_match and any(word in query_lower for word in ["stock entry", "material transfer", "manufacture"]):
            return executor.create_stock_entry_for_work_order(wo_match.group(1).upper(), confirm=is_confirm)
        
        # Delivery Note from Sales Order
        if so_match and any(word in query_lower for word in ["delivery", "ship", "deliver"]):
            return executor.create_delivery_note_from_sales_order(so_match.group(1).upper(), confirm=is_confirm)
        
        # Invoice from Delivery Note (direct DN reference)
        dn_match = re.search(r'(MAT-DN-\d+-\d+|DN-\d+)', query, re.IGNORECASE)
        if dn_match and "invoice" in query_lower:
            return executor.create_invoice_from_delivery_note(dn_match.group(1).upper(), confirm=is_confirm)
        
        # Invoice from Sales Order (finds linked DN, then creates invoice)
        if so_match and any(word in query_lower for word in ["invoice", "factura", "bill"]):
            return executor.create_invoice_from_sales_order(so_match.group(1).upper(), confirm=is_confirm)
        
        # Workflow status
        if "workflow status" in query_lower or "track" in query_lower:
            q_match = re.search(r'(SAL-QTN-\d+-\d+)', query, re.IGNORECASE)
            so_match = re.search(r'(SAL-ORD-\d+-\d+)', query, re.IGNORECASE)
            return executor.get_workflow_status(
                quotation_name=q_match.group(1).upper() if q_match else None,
                so_name=so_match.group(1).upper() if so_match else None
            )
        
        # Submit BOM: first try standard BOM doctype, then BOM Creator
        if "submit" in query_lower and "bom" in query_lower:
            bom_match = re.search(r'(BOM-[^\s]+)', query, re.IGNORECASE)
            if bom_match:
                bom_name = bom_match.group(1)
                # URL decode if needed (e.g., %2F -> /)
                import urllib.parse
                bom_name = urllib.parse.unquote(bom_name)
                
                # Try standard BOM first
                if frappe.db.exists("BOM", bom_name):
                    try:
                        bom_doc = frappe.get_doc("BOM", bom_name)
                        if bom_doc.docstatus == 0:  # Draft
                            bom_doc.submit()
                            return {
                                "success": True,
                                "message": f"✅ BOM '{bom_name}' submitted successfully!\n\n"
                                           f"  Item: {bom_doc.item}\n"
                                           f"  Qty: {bom_doc.quantity} {bom_doc.uom}\n"
                                           f"  Items: {len(bom_doc.items)}\n"
                                           f"  Status: Submitted"
                            }
                        elif bom_doc.docstatus == 1:
                            return {"success": False, "error": f"BOM '{bom_name}' is already submitted."}
                        else:
                            return {"success": False, "error": f"BOM '{bom_name}' is cancelled (docstatus=2). Cannot submit."}
                    except Exception as e:
                        return {"success": False, "error": f"Error submitting BOM '{bom_name}': {str(e)}"}
                
                # Fallback: try BOM Creator
                try:
                    from raven_ai_agent.agents.bom_creator_agent import submit_bom_creator
                    result = submit_bom_creator(bom_name)
                    if result.get("success"):
                        return {
                            "success": True,
                            "message": result.get("message", f"✅ BOM Creator '{bom_name}' submitted successfully!")
                        }
                    else:
                        return {
                            "success": False,
                            "error": result.get("error", f"'{bom_name}' not found as BOM or BOM Creator.")
                        }
                except Exception as e:
                    return {"success": False, "error": f"'{bom_name}' not found as standard BOM, and BOM Creator lookup failed: {str(e)}"}
        
        # Create BOM for Batch: @ai create bom for batch LOTE-XXXX
        if "create bom" in query_lower and ("batch" in query_lower or "lote" in query_lower):
            batch_match = re.search(r'(LOTE-[^\s]+)', query, re.IGNORECASE)
            if not batch_match:
                batch_match = re.search(r'(?:batch|lote)\s+([^\s]+)', query, re.IGNORECASE)
            
            if batch_match:
                batch_name = batch_match.group(1).upper()
                try:
                    from raven_ai_agent.agents.bom_creator_agent import create_bom_for_batch
                    result = create_bom_for_batch(batch_name)
                    if result.get("success"):
                        return {
                            "success": True,
                            "message": result.get("message", f"✅ BOM created for batch '{batch_name}'")
                        }
                    else:
                        return {
                            "success": False,
                            "error": result.get("error", "Failed to create BOM for batch")
                        }
                except Exception as e:
                    return {"success": False, "error": f"Error creating BOM for batch: {str(e)}"}
            else:
                return {"success": False, "error": "Please specify batch name: '@ai create bom for batch LOTE-XXXX'"}
        

        # === DISPATCH TO HANDLER MODULES ===
        # Manufacturing SOP
        result = self._handle_manufacturing_commands(query, query_lower, is_confirm=is_confirm)
        if result is not None:
            return result

        # BOM Commands
        result = self._handle_bom_commands(query, query_lower, is_confirm=is_confirm)
        if result is not None:
            return result

        # Direct Web Search
        result = self._handle_web_search_commands(query, query_lower)
        if result is not None:
            return result

        # Sales-to-Purchase Cycle (pass is_confirm for ! commands)
        result = self._handle_sales_commands(query, query_lower, is_confirm=is_confirm)
        if result is not None:
            return result

        # Quotation Management
        result = self._handle_quotation_commands(query, query_lower, is_confirm=is_confirm)
        if result is not None:
            return result

        return None

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
        workflow_result = self.execute_workflow_command(query, channel_id=channel_id)
        if workflow_result:
            if workflow_result.get("requires_confirmation"):
                # Store the original command for later "confirm" replay
                cache_key = f"pending_confirm:{self.user}:{channel_id}"
                frappe.cache().set_value(cache_key, query, expires_in_sec=300)  # 5 min TTL
                frappe.logger().info(f"[Workflow] Stored pending command for confirm: {query}")
                return {
                    "success": True,
                    "response": f"[CONFIDENCE: HIGH] [AUTONOMY: LEVEL 2]\n\n{workflow_result['preview']}",
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
        # Commands that fall through to LLM path (not structured workflows) also need
        # to be cached when they suggest LEVEL 2+ autonomy, so "confirm" can replay them
        is_confirm = any(word in query_lower for word in ["confirm", "yes", "proceed", "do it", "execute", "si", "confirmar"])
        if query.startswith("!"):
            is_confirm = True
        
        if suggested_autonomy >= 2 and not is_confirm:
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
            messages.extend(conversation_history[-10:])  # Last 10 messages
        
        # Add current query with autonomy context
        autonomy_warning = ""
        if suggested_autonomy >= 2:
            autonomy_warning = f"\n\n⚠️ This query suggests LEVEL {suggested_autonomy} autonomy. Please confirm before executing any changes. (Tip: Use `@ai !command` to skip confirmation)"
        
        messages.append({"role": "user", "content": query + autonomy_warning})
        
        # Call LLM
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.settings.get("max_tokens", 2000),
                temperature=0.3  # Lower temperature for accuracy
            )
            
            answer = response.choices[0].message.content
            
            # Extract facts to store (simple heuristic)
            if "[Stored:" in answer:
                # Parse and store facts
                pass
            
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
    
    def end_session(self, conversation: List[Dict]):
        """Lucy Protocol: Generate session summary"""
        if not conversation:
            return
        
        summary_prompt = "Summarize this conversation in 2-3 sentences, focusing on key decisions and information shared."
        
        messages = [
            {"role": "system", "content": summary_prompt},
            {"role": "user", "content": json.dumps(conversation[-20:], default=str)}
        ]
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=200
            )
            
            summary = response.choices[0].message.content
            
            # Store summary
            doc = frappe.get_doc({
                "doctype": "AI Memory",
                "user": self.user,
                "content": summary,
                "importance": "High",
                "memory_type": "Summary",
                "source": "Session End"
            })
            doc.insert(ignore_permissions=True)
            frappe.db.commit()
            
        except Exception:
            pass




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
        
        # Check for @ai trigger (now on plain text) — route to correct agent by intent
        if plain_text.lower().startswith("@ai"):
            query = plain_text[3:].strip()
            # Detect intent to route to specialized agents
            q_lower = query.lower()
            mfg_keywords = ["work order", "create wo", "submit wo", "manufacture", "transfer material", "check material", "mfg-wo", "wo plan", "create batch", "show work order", "list work order", "mis ordenes", "show wo", "mfg status", "mfg dashboard", "manufacturing status", "manufacturing dashboard", "finish", "!finish", "no_transfer"]
            pay_keywords = ["payment", "outstanding", "unpaid", "reconcile", "acc-sinv", "acc-pay", "sinv-"]
            orch_keywords = ["pipeline status", "run full cycle", "run pipeline", "dry run", "validate so"]
            validator_keywords = ["diagnose", "diagnosis", "validate ", "audit pipeline", "check payment", "check pago", "pipeline health", "verify so", "verify sales order", "sync so", "fix so", "sync sales order", "fix sales order", "!sync", "!fix"]
            if any(kw in q_lower for kw in validator_keywords):
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
                query = "help"  # Default if only mention
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
                query = "helicopter"  # Default to helicopter view
            bot_name = "executive"

        # Check for @iot bot
        elif "iot" in plain_text.lower():
            query = plain_text.lower().replace("@iot", "").strip()
            if not query:
                query = "help"
            bot_name = "iot"
        
        # NEW: Check for @manufacturing or @mfg bot
        elif "manufacturing" in plain_text.lower() or "@mfg" in plain_text.lower():
            query = plain_text
            for tag in ["@manufacturing", "@Manufacturing", "@mfg", "@MFG"]:
                query = query.replace(tag, "")
            query = query.strip()
            if not query:
                query = "help"
            bot_name = "manufacturing_bot"
        
        # NEW: Check for @payment bot
        elif plain_text.lower().startswith("@payment"):
            query = plain_text
            for tag in ["@payment", "@Payment"]:
                query = query.replace(tag, "")
            query = query.strip()
            if not query:
                query = "help"
            bot_name = "payment_bot"
        
        # NEW: Check for @workflow or @orchestrator or @pipeline bot
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
        frappe.logger().info(f"[AI Agent] Processing query from {user}: {query}")
        
        # Use ignore_permissions flag instead of switching user (avoids logout issue)
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
            # NEW: Manufacturing Agent
            elif bot_name == "manufacturing_bot":
                from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
                mfg_agent = ManufacturingAgent(user)
                response = mfg_agent.process_command(query)
                result = {"success": True, "response": response}
            # NEW: Payment Agent
            elif bot_name == "payment_bot":
                from raven_ai_agent.agents.payment_agent import PaymentAgent
                pay_agent = PaymentAgent(user)
                response = pay_agent.process_command(query)
                result = {"success": True, "response": response}
            # NEW: Workflow Orchestrator
            elif bot_name == "workflow_orchestrator":
                from raven_ai_agent.agents.workflow_orchestrator import WorkflowOrchestrator
                wf_agent = WorkflowOrchestrator(user)
                response = wf_agent.process_command(query)
                result = {"success": True, "response": response}
            # NEW: Task Validator / Diagnosis
            elif bot_name == "task_validator":
                from raven_ai_agent.api.handlers.task_validator import TaskValidatorMixin
                class _ValidatorAgent(TaskValidatorMixin):
                    pass
                validator = _ValidatorAgent()
                validator_result = validator._handle_validator_commands(query, query.lower())
                if validator_result:
                    result = {"success": True, "response": validator_result.get("message") or validator_result.get("error", "No result")}
                else:
                    result = {"success": False, "response": "Could not process validator command. Try: `@ai diagnose SAL-QTN-XXXX`"}
            else:
                # Try SkillRouter first for specialized skills (formulation, etc.)
                try:
                    from raven_ai_agent.skills.router import SkillRouter
                    router = SkillRouter()
                    router_result = router.route(query)
                    if router_result and router_result.get("handled"):
                        result = {"success": True, "response": router_result.get("response", "Skill executed.")}
                    else:
                        # Fallback to general agent
                        agent = RaymondLucyAgent(user)
                        result = agent.process_query(query, channel_id=doc.channel_id)
                except ImportError:
                    frappe.logger().warning("[AI Agent] SkillRouter not available, using default agent")
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
        except:
            pass
