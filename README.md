# Raven AI Agent

Raymond-Lucy AI Agent for ERPNext with Raven Integration - Enhanced with OpenClaw-inspired architecture.

## Current Status

**Latest Update:** March 2026
**Production Deployment:** Active on https://erp.sysmayal2.cloud

### Recent Deployments

| Date | Changes |
|------|---------|
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
