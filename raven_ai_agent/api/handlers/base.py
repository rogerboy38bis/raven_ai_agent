"""
Base Mixin - Core utility methods for RaymondLucyAgent

⚠️  REFERENCE COPY — NOT USED AT RUNTIME.
RaymondLucyAgent in agent.py has these methods defined inline.
This file exists for documentation. If you change agent.py's
execute_workflow_command(), update this file too for consistency.

Contains: __init__, _get_settings, get_morning_briefing, search_memories,
tattoo_fact, detect_doctype_from_query, query_doctype_with_permissions,
get_available_doctypes, duckduckgo_search, search_web, get_erpnext_context,
determine_autonomy, execute_workflow_command
"""
import frappe
import json
import re
import requests
from typing import Optional, Dict, List
from openai import OpenAI
from bs4 import BeautifulSoup

try:
    from raven_ai_agent.utils.vector_store import VectorStore
    VECTOR_SEARCH_ENABLED = True
except ImportError:
    VECTOR_SEARCH_ENABLED = False

try:
    from raven_ai_agent.api.workflows import WorkflowExecutor
    WORKFLOWS_ENABLED = True
except ImportError:
    WORKFLOWS_ENABLED = False


class BaseMixin:
    """Core utility methods - mixed into RaymondLucyAgent"""

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
    
    def execute_workflow_command(self, query: str) -> Optional[Dict]:
        """Parse and execute workflow commands"""
        frappe.logger().info(f"[Workflow] Checking query: {query}, WORKFLOWS_ENABLED: {WORKFLOWS_ENABLED}")
        
        if not WORKFLOWS_ENABLED:
            frappe.logger().info("[Workflow] Workflows disabled")
            return None
        
        query_lower = query.lower()
        executor = WorkflowExecutor(self.user)
        
        # Check for confirmation
        is_confirm = any(word in query_lower for word in ["confirm", "yes", "proceed", "do it", "execute"])
        
        # Force mode with ! prefix (like sudo)
        is_force = query.startswith("!")
        if is_force:
            is_confirm = True
            query = query.lstrip("!").strip()
            query_lower = query.lower()
        
        # Auto-confirm for privileged users (Sales Manager, etc.)
        privileged_roles = ["Sales Manager", "Manufacturing Manager", "Stock Manager", "Accounts Manager", "System Manager"]
        user_roles = frappe.get_roles(self.user)
        if any(role in user_roles for role in privileged_roles):
            is_confirm = True
        
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
        
        # Sales Order patterns — BUG15 fix: match SO-NNNNN prefix, resolve full name via DB
        so_match = re.search(r'(SAL-ORD-\d+-\d+|SO-\d{3,5})', query, re.IGNORECASE)
        if so_match:
            _so_prefix = so_match.group(1).upper()
            _so_full = frappe.db.get_value("Sales Order",
                {"name": ["like", f"{_so_prefix}%"], "docstatus": ["!=", 2]}, "name")
            if _so_full:
                class SOMatch:
                    def __init__(self, name):
                        self._name = name
                    def group(self, n=0):
                        return self._name
                so_match = SOMatch(_so_full)
        
        # Submit Sales Order
        if so_match and "submit" in query_lower and "sales order" in query_lower:
            return executor.submit_sales_order(so_match.group(1), confirm=is_confirm)
        
        # Sales Order to Work Order
        if so_match and "work order" in query_lower:
            return executor.create_work_orders_from_sales_order(so_match.group(1), confirm=is_confirm)
        
        # Stock Entry for Work Order
        wo_match = re.search(r'(MFG-WO-\d+|LOTE-\d+|P-VTA-\d+|WO-[^\s]+)', query, re.IGNORECASE)
        if wo_match and any(word in query_lower for word in ["stock entry", "material transfer", "manufacture"]):
            return executor.create_stock_entry_for_work_order(wo_match.group(1).upper(), confirm=is_confirm)
        
        # Delivery Note from Sales Order
        if so_match and any(word in query_lower for word in ["delivery", "ship", "deliver"]):
            return executor.create_delivery_note_from_sales_order(so_match.group(1), confirm=is_confirm)
        
        # Invoice from Delivery Note
        dn_match = re.search(r'(MAT-DN-\d+-\d+|DN-\d+)', query, re.IGNORECASE)
        if dn_match and "invoice" in query_lower:
            return executor.create_invoice_from_delivery_note(dn_match.group(1).upper(), confirm=is_confirm)
        
        # Workflow status
        if "workflow status" in query_lower or "track" in query_lower:
            q_match = re.search(r'(SAL-QTN-\d+-\d+)', query, re.IGNORECASE)
            so_match = re.search(r'(SAL-ORD-\d+-\d+)', query, re.IGNORECASE)
            return executor.get_workflow_status(
                quotation_name=q_match.group(1).upper() if q_match else None,
                so_name=so_match.group(1).upper() if so_match else None
            )
        
        # BOM Creator: submit bom creator BOM-XXXX
        if "submit" in query_lower and "bom" in query_lower:
            bom_match = re.search(r'(BOM-[^\s]+)', query, re.IGNORECASE)
            if bom_match:
                bom_name = bom_match.group(1)
                # URL decode if needed (e.g., %2F -> /)
                import urllib.parse
                bom_name = urllib.parse.unquote(bom_name)
                
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
                        "error": result.get("error", "Failed to submit BOM Creator")
                    }
        
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
        
