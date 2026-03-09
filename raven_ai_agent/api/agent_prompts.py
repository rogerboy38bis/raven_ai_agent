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

## 💡 LEARNED EXPERIENCES - Key Insights from Production

### Raven Channel Behavior
- **@ai mention is REQUIRED** - Commands without @ai in Raven channels are silently ignored
- **! prefix for execution** - Use !command for direct execution without confirmation
- **Mobile vs Web parity** - Raven mobile uses "Raven User" doctype, web uses "User" doctype - both must be synced

### Command Routing
- **Priority order**: Skills → Workflow Commands → LLM General Query
- **Skills auto-detect** relevant queries based on trigger keywords
- **Quality commands** use "quality" prefix: `@ai quality create nc <subject>`

### Multi-System Integration
- **amb_w_tds**: BOM tracking, Serial management, TDS/COA
- **rnd_warehouse_management**: SAP movement types (261/311), Red/Green zones
- **raven_ai_agent**: Core AI with multi-provider support

### Best Practices
- Always cite specific document names (e.g., "Sales Order SAL-ORD-2026-00001")
- Include clickable links when available
- Express confidence level explicitly: [CONFIDENCE: HIGH/MEDIUM/LOW]
- Use autonomy levels: Level 1 (Copilot) → Level 2 (Command) → Level 3 (Agent)

[Sources: Document names queried]
"""

CAPABILITIES_LIST = """
## 🤖 AMB AI Agent Capabilities

**Latest Update:** March 2026 | **Version:** 2.0

---

### 📋 Available Bots

| Bot | Purpose |
|-----|---------|
| `@ai` | General ERPNext operations, manufacturing, sales, purchasing |
| `@sales_order_follow_up` | Dedicated SO tracking and fulfillment |
| `@rnd_bot` | R&D/Formulation research, innovation tracking |
| `@bom_creator` | BOM Creator automation |

---

### 🏭 Manufacturing & Production

#### Work Order Management
- `@ai show work orders` - List active work orders
- `@ai create work order for [item] qty [n]` - Create new work order
- `@ai submit work order [WO]` - Submit/start work order
- `@ai material status for [WO]` - Check component availability (Red/Green zone)
- `@ai reserve stock for [WO]` - Reserve materials for work order

#### Production Execution
- `@ai issue materials for [WO]` - Transfer materials to WIP warehouse
- `@ai show job cards for [WO]` - List operations (linked to Project Tasks)
- `@ai update progress for [WO] qty [n]` - Report production progress
- `@ai finish work order [WO]` - Complete production & receive FG

#### Stock Entry Management
- `@ai material receipt [ITEM] qty [n] price $[x]` - Create Material Receipt
- `@ai convert [STE] to material receipt` - Convert draft to Material Receipt
- `@ai verify stock entries` - Check submitted vs draft entries
- `@ai check stock ledger` - Show recent stock ledger entries
- `@ai list batches` - Show recently created batches

---

### ✅ Quality Management System (QMS)

| Command | Description |
|---------|-------------|
| `@ai quality setup status` | View QMS configuration and status |
| `@ai quality create nc <subject>` | Create Non-Conformance report |
| `@ai quality create training <name>` | Create Training Program |
| `@ai quality create audit <subject>` | Create Internal Audit |
| `@ai quality check` | Show recent Quality Inspections |

**Verified Working (March 2026):**
- ✅ Non-Conformance: QA-NC-00020
- ✅ Internal Audit: QA-MEET-26-03-08
- ✅ Training Program: GMP Basics

---

### 📦 BOM & Batch Management (amb_w_tds)

#### BOM Tracking Commands
- `@ai bom health` - Run BOM hierarchy health check
- `@ai bom inspect <BOM>` - Inspect specific BOM structure
- `@ai bom status <ITEM>` - Get BOM status for an item
- `@ai bom issues` - List all known BOM issues
- `@ai validate bom <BOM>` - Validate BOM structure and components

#### Serial/Batch Tracking
- `@ai serial health` - Overall serial system health check
- `@ai serial status <SERIAL>` - Get status of specific serial number
- `@ai serial batch <BATCH>` - List all serials in a batch

#### BOM Creator
- `@ai show bom [NAME]` - View BOM or BOM Creator details
- `@ai !submit bom BOM-XXXX` - Submit BOM Creator to generate BOMs
- `@ai validate bom BOM-XXXX` - Validate BOM Creator before submission
- `@ai create bom from tds [TDS-NAME]` - Create BOM Creator from TDS
- `@ai create bom for batch LOTE-XXXX` - Create BOM for a Batch AMB

---

### 🏢 Warehouse Management (rnd_warehouse_management)

| Command | Description |
|---------|-------------|
| `@ai warehouse status` | Overall warehouse status and utilization |
| `@ai check zone for WO-XXXX` | Check Red/Green zone status for Work Order |
| `@ai stock balance [ITEM]` | Show current stock levels |
| `@ai show stock entry [SE]` | Details of a specific Stock Entry |

**SAP Movement Types:**
- **261 (FrontFlush)** - Goods Issue for Production
- **311 (BackFlush)** - Transfer for Kitting with dual-signature

---

### 🔄 Sales-to-Purchase Cycle

- `@ai show opportunities` - List sales opportunities
- `@ai create opportunity for [customer]` - Create new sales opportunity
- `@ai check inventory for [SO]` - Check item availability for Sales Order
- `@ai show quotations` - View your quotations
- `@ai show sales orders` - View your sales orders
- `@ai show pending deliveries` - Delivery notes, stock levels
- `@ai create delivery note for [SO]` - Ship items to customer
- `@ai create sales invoice for [SO/DN]` - Invoice the customer

**Purchase Cycle:**
- `@ai create material request for [SO]` - Create Material Request from SO
- `@ai show material requests` - List pending material requests
- `@ai create rfq from [MR]` - Create Request for Quotation
- `@ai show rfqs` - List RFQs and their status
- `@ai show supplier quotations` - List supplier quotations
- `@ai create po from [SQ]` - Create Purchase Order from Supplier Quotation
- `@ai receive goods for [PO]` - Create Purchase Receipt

---

### 🌐 Web Research & External Data

- `@ai search [topic]` - Web search for any topic
- `@ai find suppliers for [product]` - Find manufacturers/suppliers
- `@ai extract from [URL]` - Extract data from any website
- `@ai who are the players in [market]` - Market research

---

### 📝 Create ERPNext Records

- `@ai create supplier [name]` - Create basic supplier
- `@ai create supplier [name] with address` - Search web & create with address
- `@ai save this research` - Cache research to AI Memory

---

### 🔧 Workflows (Level 2-3 Autonomy)

| Command | Description |
|---------|-------------|
| `!command` | Force execute without confirmation |
| `@ai convert quotation [name] to sales order` | Document conversion |
| `@ai create work order for [item]` | Manufacturing workflows |

**Autonomy Levels:**
- **Level 1 (Copilot):** Read-only queries, suggestions
- **Level 2 (Command):** Execute with confirmation
- **Level 3 (Agent):** Multi-step autonomous workflows

---

### 📄 Document Actions

- `@ai !submit Sales Order SO-XXXX` - Submit sales order
- `@ai !submit Work Order MFG-WO-XXXX` - Submit work order
- `@ai unlink sales order from MFG-WO-XXXX` - Remove SO link from WO
- `@ai !cancel bom BOM-XXXX` - Cancel submitted BOM
- `@ai !revert bom BOM-XXXX to draft` - Reset cancelled BOM to draft
- `@ai !fix quotation SAL-QTN-XXXX` - Fix cancelled quotation
- `@ai !update quotation SAL-QTN-XXXX item ITEM-CODE` - Update quotation item

---

### 🎯 Skills (AI-Powered)

| Skill | Description |
|-------|-------------|
| **Formulation Reader** | Parse and validate formulation data from BOMs |
| **Formulation Orchestrator** | Optimize batch selection (FEFO/Cost balancing) |
| **Formulation Advisor** | Production batch selection recommendations |
| **Browser** | Web automation and data extraction |
| **IoT Sensors** | Temperature, humidity, motion monitoring |
| **Skill Creator** | Create new custom skills |

---

### 🤖 IoT Bot (@iot) - Raspberry Pi AI

Use `@iot` for direct Ollama AI access on Raspberry Pi:

| Command | Description |
|---------|-------------|
| `@iot ask <prompt>` | Ask Ollama AI |
| `@iot status` | Ollama service status |
| `@iot models` | List available models |
| `@iot pull <model>` | Pull a new model |
| `@iot sysinfo` | VPS/RPi system info |
| `@iot <anything>` | Direct AI query |

---

### 📡 IoT Sensor Manager - RPi Bots L01-L30

**Supported Sensors:** Temperature (DHT22), Humidity, Motion (HC-SR501), Light (BH1750)

| Command | Description |
|---------|-------------|
| `@ai sensor status` | All sensors status |
| `@ai temperature L01` | Temperature from bot L01 |
| `@ai humidity L05` | Humidity from bot L05 |
| `@ai motion L10` | Motion detection on L10 |
| `@ai sensor history L02` | Historical readings |
| `@ai sensor alert` | Active sensor alerts |
| `@ai read sensor L03` | Read all sensors on L03 |
| `@ai bot L07 status` | Full status for bot L07 |

**Sensor Thresholds:**
- Temperature: 15-35°C (Warning), <5°C or >45°C (Critical)
- Humidity: 20-80% (Warning), <10% or >95% (Critical)
- Light: 50-800 lux (Warning)

---

### 📊 Phase 4: Advanced Analytics (Coming Soon)

- Dashboard Widgets for Raven
- Smart Aggregations (AI-powered data summarization)
- Scheduled Reports (automated generation & distribution)
- Alert Rules Engine (configurable business alerts)

---

### ℹ️ Help

- `@ai help` or `@ai capabilities` - Show this list
- `@ai what can you do` - Show capabilities

---

**Note:** Always use `@ai !command` format in Raven channels. Commands with `!` prefix execute directly without confirmation.

Type your question and I'll help!
"""
