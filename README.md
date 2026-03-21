# Raven AI Agent

Raymond-Lucy AI Agent for ERPNext with Raven Integration - Enhanced with OpenClaw-inspired architecture.

## Current Status

**Latest Update:** March 2026 | **Version:** 2.1
**Production Deployment:** Active on https://erp.sysmayal2.cloud

### Recent Deployments

| Date | Changes |
|------|---------|
| 2026-03-21 | Pipeline diagnosis commands (@ai pipeline, @ai diagnose), Payment Agent, Manufacturing workflow |
| 2026-03-20 | Data Quality Scanner, Sample Request from Lead/Prospect/Opportunity/Quotation/SO |
| 2026-03-19 | Payment Entry creation and submission fixes, @ai payment routing |
| 2026-03-09 | Sales Invoice workflow fixes (mode_of_payment field), command routing corrections |
| 2026-03-09 | Quality Management System (QMS) field bug fixes |
| 2026-03-08 | Raven User synchronization for mobile/web parity |
| 2026-03-08 | Phase 4 Advanced Analytics & Reporting module initiated |

## Features

### Core Protocols

- **Raymond Protocol**: Anti-hallucination with verified ERPNext data
- **Memento Protocol**: Persistent memory storage across sessions
- **Lucy Protocol**: Context continuity with morning briefings
- **Karpathy Protocol**: Autonomy slider (Copilot → Command → Agent)

### Multi-Provider LLM Support

| Provider | Models | Features |
|----------|--------|----------|
| **OpenAI** | gpt-4o, gpt-4o-mini, gpt-4-turbo | Default provider |
| **DeepSeek** | deepseek-chat, deepseek-reasoner | Cost-effective, reasoning mode |
| **Claude** | claude-3-5-sonnet, claude-3-opus | Strong analysis |
| **MiniMax** | abab6.5-chat, abab5.5-chat | Multilingual |

### Multi-Channel Gateway

- **Raven (Primary)**: Native ERPNext chat integration with AI commands
- **WhatsApp Business API**: Full messaging + interactive buttons
- **Telegram Bot**: Messages, voice, inline keyboards
- **Slack**: Direct messages, app mentions, button actions
- **Session Management**: Cross-channel context preservation

### Voice Integration

- **ElevenLabs TTS**: Text-to-speech responses
- **Multiple Voices**: Rachel, Drew, Bella, and more
- **Auto Voice Detection**: Respond with voice when appropriate

### Skills Platform

- **Browser Control**: Web automation and data extraction
- **Extensible Architecture**: Easy to add new skills
- **Intent Routing**: Automatic skill matching

### Quality Management System (QMS)

The QMS module provides comprehensive quality control capabilities through Raven AI commands:

| Command | Description |
|---------|-------------|
| `@ai quality setup status` | View QMS configuration and status |
| `@ai quality create nc <subject>` | Create Non-Conformance report |
| `@ai quality create training <name>` | Create Training Program |
| `@ai quality create audit <subject>` | Create Internal Audit |

**Verified Working (March 2026):**
- ✅ Non-Conformance Creation: QA-NC-00020
- ✅ Internal Audit Creation: QA-MEET-26-03-08
- ✅ Training Program Creation: GMP Basics

### Pipeline & Diagnosis Commands

Full sales pipeline management from Quotation to Delivery:

| Command | Description |
|---------|-------------|
| `@ai pipeline SAL-QTN-XXXX` | Full pipeline diagnosis with status |
| `@ai diagnose SAL-QTN-XXXX` | Detailed diagnosis with issues and next steps |
| `@ai check data SAL-QTN-XXXX` | Validate quotation data quality |
| `@ai fix SAL-QTN-XXXX` | Auto-fix data quality issues |
| `@ai scan SAL-QTN-XXXX` | Full data quality scan |
| `@ai validate SAL-QTN-XXXX` | Validate data integrity |
| `@ai repair SAL-QTN-XXXX` | Auto-repair issues |
| `@ai validate ACC-SINV-XXXXX` | Validate sales invoice |
| `@ai !fix SAL-QTN-XXXXX` | Fix cancelled quotation |
| `@ai !update quotation SAL-QTN-XXXX item ITEM-CODE` | Update quotation item |

**Pipeline Stages:**
- Quotation → Sales Order → Work Order → Stock Entry → Delivery Note → Sales Invoice → Payment

### Sales-to-Purchase Full Cycle

Complete sales pipeline from opportunity to payment and purchase requisition:

#### Sales Cycle
| Command | Description |
|---------|-------------|
| `@ai show opportunities` | List sales opportunities |
| `@ai create opportunity for [customer]` | Create new sales opportunity |
| `@ai check inventory for [SO]` | Check item availability for Sales Order |
| `@ai show quotations` | View your quotations |
| `@ai show sales orders` | View your sales orders |
| `@ai show pending deliveries` | Delivery notes, stock levels |
| `@ai create delivery note for [SO]` | Ship items to customer |
| `@ai create sales invoice for [SO/DN]` | Invoice the customer |

#### Purchase Cycle
| Command | Description |
|---------|-------------|
| `@ai create material request for [SO]` | Create Material Request from SO |
| `@ai show material requests` | List pending material requests |
| `@ai create rfq from [MR]` | Create Request for Quotation |
| `@ai show rfqs` | List RFQs and their status |
| `@ai show supplier quotations` | List supplier quotations |
| `@ai create po from [SQ]` | Create Purchase Order from Supplier Quotation |
| `@ai receive goods for [PO]` | Create Purchase Receipt |

### Payment Management Agent

Complete payment workflow automation:

| Command | Description |
|---------|-------------|
| `@ai payment create [SI-NAME]` | Create Payment Entry from Sales Invoice |
| `@ai payment create [SI-NAME] amount [AMOUNT]` | Partial payment |
| `@ai payment submit [PE-NAME]` | Submit Payment Entry |
| `@ai payment reconcile [PE-NAME]` | Check reconciliation status |
| `@ai payment outstanding` | List all unpaid invoices |
| `@ai payment outstanding customer [NAME]` | Unpaid for specific customer |
| `@ai payment status [PE-NAME]` | Payment Entry details |
| `@ai create payment for ACC-SINV-XXXX` | Create Payment Entry from Sales Invoice |
| `@ai validate ACC-SINV-XXXX` | Validate sales invoice |

**Full Payment Cycle:**
```
@ai payment create ACC-SINV-2026-00001
@ai payment submit ACC-PAY-2026-00001
@ai payment reconcile ACC-PAY-2026-00001
```

### Manufacturing Workflow Agent

Automated manufacturing from Sales Order:

| Command | Description |
|---------|-------------|
| `@ai work order from SO-XXXXX` | Create Work Order from Sales Order |
| `@ai transfer materials` | Transfer raw materials to WIP |
| `@ai manufacture MFG-WO-XXXXX` | Complete manufacturing |
| `@ai submit wo MFG-WO-XXXXX` | Submit Work Order |
| `@ai !submit Work Order MFG-WO-XXXX` | Submit Work Order (direct) |
| `@ai !submit bom BOM-XXXX` | Submit Bill of Materials |
| `@ai unlink sales order from MFG-WO-XXXX` | Remove SO link from Work Order |
| `@ai !cancel bom BOM-XXXX` | Cancel submitted BOM |
| `@ai !revert bom BOM-XXXX to draft` | Reset cancelled BOM to draft |

### Sample Request Management

Create Sample Requests from any source document via button or command:

| Command | Description |
|---------|-------------|
| `Create → Sample Request` button | Lead, Prospect, Opportunity, Quotation, Sales Order |
| `@ai sample request Lead LEAD-NAME` | Create sample request from Lead |
| `@ai sample request Prospect PROSPECT-NAME` | Create sample request from Prospect |
| `@ai sample request Opportunity OPP-NAME` | Create sample request from Opportunity |
| `@ai sample request Quotation SAL-QTN-XXXX` | Create sample request from Quotation |
| `@ai sample request Sales Order SO-XXXX` | Create sample request from Sales Order |

**Features:**
- Auto-populates party, contact, address
- Default item selection based on source type
- Request type mapping: Marketing, Prospect, Pre-sample Approved, Representative Sample, Exhibition

### Data Quality Scanner

Pre-flight validation and repair:

| Command | Description |
|---------|-------------|
| `@ai scan SAL-QTN-XXXX` | Full data quality scan |
| `@ai validate SAL-QTN-XXXX` | Validate data integrity |
| `@ai repair SAL-QTN-XXXX` | Auto-repair issues |

### Cost Monitoring

- **Usage Tracking**: Per-user token consumption
- **Budget Alerts**: Warnings when approaching limits

## Comparison: raven_ai_agent vs OpenClaw

| Feature | raven_ai_agent | OpenClaw |
|---------|---------------|----------|
| **Integration** | Frappe/Raven + Multi-channel | Multi-channel only |
| **Architecture** | Gateway + Session Management | Gateway/WebSocket |
| **AI Backend** | OpenAI + DeepSeek + Claude + MiniMax | Claude + OpenAI + local |
| **Channels** | Raven, WhatsApp, Telegram, Slack | WhatsApp, Telegram, Slack |
| **Voice** | ElevenLabs TTS | ElevenLabs |
| **Skills** | Browser control, extensible | Browser, canvas, device |
| **Cost Monitor** | ✅ Built-in | ❌ |
| **ERPNext Native** | ✅ | ❌ |

## Installation

```bash
bench get-app https://github.com/your-repo/raven_ai_agent
bench --site your-site install-app raven_ai_agent
```

## Configuration

### AI Agent Settings

1. Go to **AI Agent Settings** in ERPNext
2. Select **Default Provider** and enter API keys
3. Set **Fallback Provider** for automatic failover
4. Configure **Cost Budget** for usage warnings

### Channel Configuration (Optional)

```python
# WhatsApp
whatsapp_config = {
    "phone_number_id": "YOUR_ID",
    "access_token": "YOUR_TOKEN",
    "verify_token": "YOUR_VERIFY_TOKEN"
}

# Telegram
telegram_config = {"bot_token": "YOUR_BOT_TOKEN"}

# Slack  
slack_config = {
    "bot_token": "xoxb-YOUR-TOKEN",
    "signing_secret": "YOUR_SECRET"
}
```

### Voice Configuration (Optional)

```python
voice_config = {
    "elevenlabs_api_key": "YOUR_KEY",
    "default_voice": "rachel"
}
```

## Usage

### In Raven

```
@ai What are my pending sales invoices?
@ai Show me top customers by revenue
@ai quality setup status
@ai !quality create training GMP Basics
```

### Via API

```python
from raven_ai_agent.api.agent_v2 import process_message_v2

result = process_message_v2("What invoices are due?")
result = process_message_v2("Analyze data", provider="claude")
```

### Multi-Channel

```python
from raven_ai_agent.channels import get_channel_adapter
from raven_ai_agent.gateway import session_manager

adapter = get_channel_adapter("whatsapp", config)
incoming = adapter.parse_webhook(payload)
session = session_manager.get_or_create_session(user_id, "whatsapp", incoming.channel_user_id)
```

### Voice

```python
from raven_ai_agent.voice import ElevenLabsVoice

tts = ElevenLabsVoice(api_key="YOUR_KEY")
audio = tts.text_to_speech("Hello!")
```

## Autonomy Levels

| Level | Name | Description |
|-------|------|-------------|
| 1 | Copilot | Read-only queries, suggestions |
| 2 | Command | Execute with confirmation (use `!` prefix) |
| 3 | Agent | Multi-step autonomous workflows |

**Important:** Commands with `!` prefix execute directly without confirmation. Always use `@ai !command` format in Raven channels.

## Architecture

```
raven_ai_agent/
├── api/
│   ├── agent.py           # V1 API
│   ├── agent_v2.py        # V2 API (Multi-provider)
│   ├── workflows.py       # Business workflow automation
│   └── command_router.py  # Command routing logic
├── handlers/
│   └── quality_management.py  # QMS command handlers
├── providers/             # LLM Providers
│   ├── openai_provider.py
│   ├── deepseek.py
│   ├── claude.py
│   └── minimax.py
├── gateway/               # Multi-channel control
│   ├── session_manager.py
│   └── router.py
├── channels/              # Channel adapters
│   ├── whatsapp.py
│   ├── telegram.py
│   └── slack.py
├── voice/                 # Voice integration
│   └── elevenlabs.py
├── skills/                # Extensible skills
│   └── browser.py
└── utils/
    ├── memory.py
    └── cost_monitor.py
```

## Phase 4: Advanced Analytics & Reporting Module

**Status:** In Development (March 2026)

### Planned Features

| Feature | Description |
|---------|-------------|
| Dashboard Widgets | Custom analytics widgets for Raven |
| Smart Aggregations | AI-powered data summarization |
| Scheduled Reports | Automated report generation and distribution |
| Alert Rules Engine | Configurable business alerts |

## Formulation Orchestrator

Intelligent batch selection and formulation optimization for perishable inventory management in manufacturing environments.

### Overview

The Formulation Orchestrator is a multi-agent system designed to optimize batch selection for production orders, balancing FEFO (First Expiry, First Out) compliance with cost efficiency.

### Agent Architecture

| Phase | Agent | Purpose |
|-------|-------|----------|
| 1 | **Formulation Reader** | Parse and validate formulation data from ERPNext BOMs |
| 2 | **Batch Selector** | Query and filter available inventory batches |
| 3 | **TDS Compliance Checker** | Verify Technical Data Sheet requirements |
| 4 | **Cost Calculator** | Analyze batch costs and valuation methods |
| 5 | **Optimization Engine** | Multi-strategy batch selection optimization |
| 6 | **Report Generator** | Production-ready output formatting |

### Optimization Strategies

- **FEFO Cost Balanced** (Default): Hybrid approach balancing expiry dates with cost optimization
- **Minimize Cost**: Pure cost optimization for budget-conscious selections
- **Strict FEFO**: Guarantees full FEFO compliance
- **Minimum Batches**: Reduces picking complexity by minimizing batch count

### Key Features

- **What-If Scenarios**: Compare all strategies before committing to a selection
- **Constraint Satisfaction**: Shelf life requirements, warehouse filters, batch exclusions
- **Cost Integration**: Leverages Phase 4 cost trends for intelligent weighting
- **FEFO Violation Detection**: Automatic tracking and reporting

### Documentation

Complete project documentation is available in `docs/project_formulation/`:
- Phase implementation reports
- Technical specifications
- Agent communication protocols
- Unit test specifications

## Known Issues & Resolutions

| Issue | Status | Resolution |
|-------|--------|------------|
| Mobile/Web channel visibility mismatch | ✅ Fixed | Sync Raven User table with ERPNext User |
| Sales Invoice creation failure | ✅ Fixed | Added mode_of_payment field to workflow |
| Command routing for !prefix | ✅ Fixed | Updated command_router.py |
| QMS Training Program field bug | ✅ Fixed | Field validation updates |

---

## License

MIT
