# Multi-Agent Orchestration Specification

## Phase 8B - Multi-Agent Orchestration & Context Memory

This document describes the multi-agent orchestration architecture introduced in Phase 8B.

## Overview

Complex queries in ERPNext often span multiple domains - a sales order may require checking manufacturing status, delivery progress, and payment history simultaneously. The multi-agent orchestration layer enables coordinated execution across multiple specialized agents while maintaining conversation context.

### Why Multi-Agent Orchestration?

1. **Complex Queries**: Commands like "full status SO-0001" require data from sales, manufacturing, and payment domains
2. **Workflows**: "workflow run SO-0001" triggers sequential processing across multiple agents
3. **Context Awareness**: The system remembers previous interactions within a session
4. **Event-Driven**: Agents can communicate through a shared event bus

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User Message                                │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    router.py (handle_raven_message)                │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Phase 7: Intent Resolver (NL → command)                     │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                  │                                 │
│                                  ▼                                 │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Phase 8B: Multi-Agent Router (is_multi_agent_command?)      │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                  │                                 │
│                                  ▼                                 │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
                    ▼                           ▼
         ┌──────────────────┐      ┌──────────────────────────┐
         │ ContextStore     │      │ AgentBus                 │
         │ (Session Context)│      │ (Event Pub/Sub)          │
         └──────────────────┘      └──────────────────────────┘
                    │                           │
                    └─────────────┬─────────────┘
                                  │
                                  ▼
                    ┌─────────────────────────────┐
                    │     Agent Pipeline          │
                    │  ┌───────┐ ┌───────┐       │
                    │  │Sales  │ │Mfg   │ ┌────┐ │
                    │  │Order  │ │ WO   │ │Pay │ │
                    │  └───────┘ └───────┘ └────┘ │
                    └─────────────────────────────┘
```

## Components

### 1. Context Manager (`utils/context_manager.py`)

Provides persistent session context for each user with TTL (Time-To-Live) support.

#### SessionContext Class

Stores per-user conversation state:

| Field | Type | Description |
|-------|------|-------------|
| user | str | User identifier |
| last_intent | str | Last resolved intent |
| last_document | str | Last referenced document |
| last_agent | str | Last agent used |
| last_command | str | Last command string |
| session_start | datetime | Session creation time |
| turn_count | int | Number of interactions |
| context_data | dict | Arbitrary agent data |

**Key Methods:**

- `update(intent, document, agent, command, **kwargs)` - Update context and increment turn count
- `get_context()` - Get all context as dictionary
- `clear()` - Reset to initial state
- `is_follow_up(new_intent)` - Check if new intent relates to last intent

**Follow-up Relations:**

```python
FOLLOW_UP_RELATIONS = {
    'list': {'status', 'detail', 'info'},
    'status': {'diagnose', 'detail', 'info'},
    'diagnose': {'fix', 'workflow', 'action'},
    'payment': {'status', 'detail', 'check'},
    'workflow': {'run', 'execute', 'start'},
}
```

#### ContextStore Class

In-memory session storage with TTL:

- **TTL**: 30 minutes of inactivity
- **Singleton**: Shared instance across the application
- **Thread-safe**: Uses locks for concurrent access

**Key Methods:**

- `get_or_create(user)` - Get or create session for user
- `cleanup_expired()` - Remove sessions older than 30 minutes
- `get_active_session_count()` - Get number of active sessions

### 2. Agent Bus (`utils/agent_bus.py`)

Event-driven inter-agent communication system.

#### AgentEvent Class

| Field | Type | Description |
|-------|------|-------------|
| event_type | str | Event type (e.g., EVENT_SO_UPDATED) |
| source_agent | str | Emitting agent name |
| target_agent | str | Optional target agent |
| payload | dict | Event data |
| timestamp | datetime | Creation timestamp |
| correlation_id | str | UUID for tracing |

#### Event Constants

```python
EVENT_SO_UPDATED = "sales_order_updated"
EVENT_WO_CREATED = "work_order_created"
EVENT_PAYMENT_PROCESSED = "payment_processed"
EVENT_AGENT_ERROR = "agent_error"
EVENT_WORKFLOW_TRIGGERED = "workflow_triggered"
EVENT_AGENT_START = "agent_start"
EVENT_AGENT_COMPLETE = "agent_complete"
EVENT_DOCUMENT_CREATED = "document_created"
EVENT_DOCUMENT_UPDATED = "document_updated"
```

#### AgentBus Class

Singleton pub/sub event bus:

- **Queue**: collections.deque with maxlen=500
- **Thread-safe**: Uses locks for queue and handler operations

**Key Methods:**

- `publish(event)` - Add event to queue
- `subscribe(event_type, handler)` - Register handler
- `unsubscribe(event_type, handler)` - Remove handler
- `dispatch(event)` - Call all handlers for event type
- `publish_and_dispatch(event)` - Publish and dispatch in one call

### 3. Multi-Agent Router (`api/multi_agent_router.py`)

Routes complex commands to appropriate agent pipelines.

#### Supported Commands

| Command Pattern | Pipeline Type | Steps |
|----------------|---------------|-------|
| `workflow run SO-XXXX` | workflow_run | sales_order_followup → manufacturing → payment |
| `execute workflow SO-XXXX` | workflow_run | sales_order_followup → manufacturing → payment |
| `full status SO-XXXX` | full_status | sales status → delivery status → payment status |
| `complete status SO-XXXX` | full_status | sales status → delivery status → payment status |
| `detailed status SO-XXXX` | full_status | sales status → delivery status → payment status |
| `diagnose and fix SO-XXXX` | diagnose_and_fix | diagnose → validate → suggest actions |
| `diagnose & fix SO-XXXX` | diagnose_and_fix | diagnose → validate → suggest actions |
| `morning briefing` | morning_briefing | sales summary → pending WOs → overdue payments |
| `daily briefing` | morning_briefing | sales summary → pending WOs → overdue payments |
| `briefing` | morning_briefing | sales summary → pending WOs → overdue payments |

#### Key Functions

- `is_multi_agent_command(command)` - Check if command needs multiple agents
- `build_agent_pipeline(command)` - Get ordered list of agent steps
- `execute_pipeline(pipeline, user, context)` - Run pipeline steps
- `handle_multi_agent_command(command, user)` - Entry point

## Pipeline Execution Flow

```
User Command
    │
    ▼
is_multi_agent_command() ──No──▶ Normal Routing
    │ Yes
    ▼
build_agent_pipeline()
    │
    ▼
For each step:
    │
    ├─▶ Publish EVENT_AGENT_START
    │
    ├─▶ Execute agent (via router.handle_raven_message)
    │
    ├─▶ Publish EVENT_AGENT_COMPLETE or EVENT_AGENT_ERROR
    │
    └─▶ Add result to accumulated context
    │
    ▼
Aggregate responses
    │
    ▼
Update ContextStore
    │
    ▼
Return formatted response
```

### Error Handling

- **Non-fatal**: Pipeline continues on step failure
- **Logging**: Errors are logged for debugging
- **Event Publishing**: Errors trigger EVENT_AGENT_ERROR

## Integration Points

### Phase 7 (Intent Resolver)

The multi-agent router integrates **after** intent resolution:

```python
# Phase 7: Intent resolution
resolved_command = resolve_intent_message(query)

# Phase 8B: Multi-agent check (after intent resolution)
multi_result = handle_multi_agent_command(resolved_command, user)
if multi_result is not None:
    return multi_result
```

### Phase 8A (Truth Hierarchy)

The context and events can be used with truth hierarchy validation:

- Context data can be passed to `validate_and_sanitize()` for fact-checking
- Agent events enable tracing for audit trails

## Adding New Pipeline Commands

### Step 1: Add Pattern

In `multi_agent_router.py`, add to `MULTI_AGENT_PATTERNS`:

```python
(r'^new\s+command\s+SO-', 'new_pipeline_type'),
```

### Step 2: Add Pipeline Builder

In `build_agent_pipeline()`:

```python
elif pipeline_type == 'new_pipeline_type':
    return [
        {"agent": "agent1", "sub_command": f"step1 {so_name}"},
        {"agent": "agent2", "sub_command": f"step2 {so_name}"},
    ]
```

### Step 3: Add Tests

Add test cases to `tests/test_multi_agent.py`:

```python
def test_build_pipeline_new_command(self):
    pipeline = build_agent_pipeline("new command SO-0001")
    self.assertEqual(len(pipeline), 2)
```

## Adding New Event Types

### Step 1: Define Constant

In `agent_bus.py`:

```python
EVENT_NEW_TYPE = "new_event_type"
```

### Step 2: Publish Event

```python
from raven_ai_agent.utils.agent_bus import AgentEvent, get_bus

bus = get_bus()
bus.publish_and_dispatch(AgentEvent(
    event_type=EVENT_NEW_TYPE,
    source_agent="my_agent",
    payload={"key": "value"}
))
```

### Step 3: Subscribe to Event

```python
def my_handler(event):
    print(f"Received: {event.payload}")

bus.subscribe(EVENT_NEW_TYPE, my_handler)
```

## ContextStore TTL Behavior

- **Creation**: Session starts when user sends first message
- **Activity**: Each message updates `_last_update` timestamp
- **Expiration**: Sessions expire after 30 minutes of inactivity
- **Cleanup**: `cleanup_expired()` removes expired sessions
- **Access**: `get_or_create()` always returns valid session (creates new if needed)

## Testing

Run all tests:

```bash
cd ~/frappe-bench/apps/raven_ai_agent
python -m pytest tests/test_multi_agent.py -v
```

Expected: **25 tests PASS**

Run all project tests:

```bash
python -m pytest tests/ -v
```

Expected: **139+ tests PASS** (114 original + 25 new)

## File Locations

| Component | Path |
|-----------|------|
| Context Manager | `raven_ai_agent/utils/context_manager.py` |
| Agent Bus | `raven_ai_agent/utils/agent_bus.py` |
| Multi-Agent Router | `raven_ai_agent/api/multi_agent_router.py` |
| Router Integration | `raven_ai_agent/api/router.py` |
| Tests | `tests/test_multi_agent.py` |

## Related Documentation

- [Phase 8A: Anti-Hallucination](./ANTI_HALLUCINATION_SPEC.md)
- [Phase 7: Intent Resolver](./INTENT_RESOLVER_SPEC.md)
- [Deployment Guide](./DEPLOYMENT_GUIDE.md)
- [Monitoring & Alerting](./MONITORING_ALERTING.md)
