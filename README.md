# Raven AI Agent

Raymond-Lucy AI Agent for ERPNext with Raven Integration - Enhanced with OpenClaw-inspired architecture and an Agentic-Design-Patterns intelligence layer.

## Current Status

**Latest Update:** May 2026 | **Version:** 2.2
**Production Deployment:** Active on https://erp.sysmayal2.cloud

### Recent Deployments

| Date | Changes |
|------|---------|
| 2026-05-01 | Agentic Design Patterns intelligence layer (Reflection, Planner, Coordinator, Goal Loop, Fallback, RAG, Guardrails) wired into agent_v2 (PR #3) |
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
- **Agentic Design Patterns Layer**: 7 provider-agnostic patterns (Reflection, Planner, Coordinator, Goal Loop, Fallback, RAG, Guardrails) that boost the agent's reasoning, planning and safety — see [Intelligence Layer](#intelligence-layer-agentic-design-patterns)

### Multi-Provider LLM Support

| Provider | Models | Features |
|----------|--------|----------|
| **OpenAI** | gpt-4o, gpt-4o-mini, gpt-4-turbo | Default provider |
| **DeepSeek** | deepseek-chat, deepseek-reasoner | Cost-effective, reasoning mode |
| **Claude** | claude-3-5-sonnet, claude-3-opus | Strong analysis |
| **MiniMax** | abab6.5-chat, abab5.5-chat | Multilingual |
| **Ollama** | llama3.x, qwen, mistral, etc. | On-prem / offline |

All five providers transparently work with the **FallbackChain** pattern — if the primary provider fails or returns empty, the chain falls through to the next one in your configured order.

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
│   ├── agent.py             # V1 API (Raymond / Lucy / Memento)
│   ├── agent_v2.py          # V2 API (multi-provider + intelligence layer)
│   ├── workflows.py         # Business workflow automation
│   ├── command_router.py    # Command routing logic
│   ├── multi_agent_router.py  # Regex pipelines + Coordinator semantic fallback
│   ├── intent_resolver.py   # NL → command
│   └── memory_manager.py    # Persistent memory + vector search
├── patterns/                # Agentic Design Patterns intelligence layer
│   ├── reflection.py        # Producer / critic loop (Ch. 4)
│   ├── planner.py           # JSON plan decomposition (Ch. 6)
│   ├── coordinator.py       # Semantic multi-agent routing (Ch. 7)
│   ├── goal_loop.py         # Goal + criteria iteration (Ch. 11)
│   ├── fallback.py          # Provider / tool fallback chain (Ch. 12)
│   ├── rag_retriever.py     # Retrieve-and-ground answers (Ch. 14)
│   ├── guardrails.py        # Pre-mutation safety rules (Ch. 18)
│   ├── intelligence.py      # IntelligenceLayer façade used by agent_v2
│   └── tests/
│       └── test_patterns_smoke.py  # 8 control-flow tests, no Frappe needed
├── agents/                  # Specialist agents (workflow_orchestrator, task_validator, …)
├── handlers/
│   └── quality_management.py  # QMS command handlers
├── providers/               # LLM providers (OpenAI, DeepSeek, Claude, MiniMax, Ollama)
├── gateway/                 # Multi-channel control (session_manager, router)
├── channels/                # Channel adapters (whatsapp, telegram, slack)
├── voice/                   # Voice integration (elevenlabs)
├── skills/                  # Extensible skills (browser, …)
└── utils/
    ├── memory.py
    ├── vector_store.py      # Used by RAGRetriever
    └── cost_monitor.py
```

## Intelligence Layer (Agentic Design Patterns)

The `raven_ai_agent/patterns/` module brings seven patterns from
[evoiz/Agentic-Design-Patterns](https://github.com/evoiz/Agentic-Design-Patterns)
(Antonio Gulli's *Agentic Design Patterns* book) into the agent. The layer is
**provider-agnostic**, **opt-in**, and only activated for queries flagged as
complex — it never changes existing behaviour when disabled.

### Patterns at a glance

| Pattern | Module | Book ch. | Raven use case |
|---|---|---:|---|
| Reflection | `reflection.py` | 4 | Critic-revise BOMs, pipeline diagnosis answers |
| Planner | `planner.py` | 6 | Decompose "QTN → paid invoice" into ordered command steps |
| Coordinator | `coordinator.py` | 7 | Semantic agent routing when regex patterns miss |
| Goal Loop | `goal_loop.py` | 11 | Iterate until ERPNext truth-checks pass (Raymond anti-hallucination) |
| Fallback | `fallback.py` | 12 | Graceful provider degradation across all five LLM providers |
| RAG Retriever | `rag_retriever.py` | 14 | Ground answers in `MemoryMixin.search_memories` with `[#n]` citations |
| Guardrails | `guardrails.py` | 18 | Pre-mutation safety checks tied to the autonomy slider |

### How it plugs into agent_v2

During `process_query`, the agent consults the layer at four extension points:

1. **Classify complexity** — rule-based, free, every query.
2. **RAG short-circuit** — when complexity = `rag`, the answer is grounded in
   AI Memories with `[#1]`, `[#2]` citations and tagged
   `[CONFIDENCE: HIGH] [PATTERN: RAG]`.
3. **Plan injection** — when complexity = `planning`, a numbered Plan is
   prepended to the system prompt as the answer's backbone.
4. **Post-LLM Reflection** — at autonomy ≥ Command, the draft is critic-revised
   once against criteria like "no fabricated doc IDs / totals / dates".

Responses now expose new `context_used` keys: `complexity`, `plan_preview`,
`reflection_accepted`, and `pattern: rag` for retrieval-grounded replies.

### Default Guardrail rules

| Rule | Severity |
|---|---|
| `submit_requires_target` | High |
| `payment_currency_match` | High |
| `quotation_so_field_match` (CRITICAL_FIELDS divergence) | High |
| `bulk_requires_ack` (≥ 25 docs without confirmation) | Medium |
| `copilot_blocks_mutation` | High |

Add custom rules with:
```python
from raven_ai_agent.patterns import Guardrails
Guardrails().register(my_rule_fn)
```

### Enabling the layer

Pick one:

**Option A — environment flag (recommended for ops):**
Add to **every** `[program:...]` block in `/etc/supervisor/conf.d/frappe-bench.conf`:
```
environment=RAVEN_INTELLIGENCE_LAYER="1"
```
Then:
```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl restart frappe-bench-web: frappe-bench-workers:
```

**Option B — per-site setting:**
In ERPNext UI → *AI Agent Settings* → check **Intelligence Layer Enabled**.

Verify the env var actually reached a worker:
```bash
ps -ef | grep -E "/home/frappe/frappe-bench/env/bin/gunicorn.*127\.0\.0\.1:8000" | grep -v grep
sudo cat /proc/<gunicorn-pid>/environ | tr '\0' '\n' | grep RAVEN
# expect: RAVEN_INTELLIGENCE_LAYER=1
```

The activation log line confirms the layer is live:
```
[AI Agent V2] IntelligenceLayer activated
```

### Triggering each pattern from chat

| Type this in Raven | Pattern triggered |
|---|---|
| `Take SAL-QTN-XXXX all the way to a paid invoice` | Planner |
| `According to previous sessions, what was the last quotation we worked on` | RAG |
| `Audit SO-XXXXX totals and verify nothing is fabricated` | Reflection (autonomy ≥ Command) |
| `Diagnose and fix the pipeline gap on SO-XXXXX` | Coordinator semantic fallback |

### Smoke tests

The pattern module ships an 8-test smoke suite using a scripted `FakeProvider`
— no Frappe, no API keys, no network needed:
```bash
cd ~/frappe-bench/apps/raven_ai_agent
python -m raven_ai_agent.patterns.tests.test_patterns_smoke
# All pattern smoke tests passed.
```

Full architecture and per-pattern reference: [`docs/AGENTIC_PATTERNS.md`](docs/AGENTIC_PATTERNS.md).

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
| `bench --site all clear-cache` MariaDB access denied | ⚠️ Workaround | DB credentials in `sites/<site>/site_config.json` no longer match MariaDB. Patterns layer is unaffected; fix by updating `db_password` to match the actual DB user. |
| Socketio `EADDRINUSE` after supervisor reload | ✅ Tooling | Run `./bench_socketio_doctor.sh --fix` (and `--restart-all` if needed) to free port 9000 and respawn. |

## Operations cheat sheet

```bash
# Restart bench cleanly via supervisor (web + workers)
sudo supervisorctl restart frappe-bench-web: frappe-bench-workers:

# Heal socketio if it goes ERROR (spawn error)
./bench_socketio_doctor.sh --fix

# Confirm intelligence layer is live in a running worker
ps -ef | grep -E "/home/frappe/frappe-bench/env/bin/gunicorn.*127\.0\.0\.1:8000" | grep -v grep
sudo cat /proc/<pid>/environ | tr '\0' '\n' | grep RAVEN

# Smoke-test the patterns module (no Frappe needed)
cd ~/frappe-bench/apps/raven_ai_agent
python -m raven_ai_agent.patterns.tests.test_patterns_smoke

# Tail intelligence layer logs while testing
cd ~/frappe-bench
tail -f logs/web.log logs/worker.log 2>/dev/null | grep -i "intelligence\|AI Agent V2\|PATTERN"
```

---

## License

MIT
