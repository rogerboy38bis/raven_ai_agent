"""
Agent Prompts and Constants
Split from agent.py - Phase 2 Optimization

Contains: SYSTEM_PROMPT, CAPABILITIES_LIST
"""

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

CAPABILITIES_LIST = """## 🤖 AI Agent Capabilities

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
