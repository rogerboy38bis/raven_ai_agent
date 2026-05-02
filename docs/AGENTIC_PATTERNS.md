# Agentic Design Patterns in Raven AI Agent

This module brings seven patterns from Antonio Gulli's *Agentic Design Patterns:
A Hands-On Guide to Building Intelligent Systems*
([evoiz/Agentic-Design-Patterns](https://github.com/evoiz/Agentic-Design-Patterns))
into the Raven agent.  All patterns are **provider-agnostic** — they take any
`LLMProvider` (OpenAI, DeepSeek, Claude, MiniMax, Ollama) — and **opt-in** via
`AI Agent Settings.intelligence_layer_enabled` or the env flag
`RAVEN_INTELLIGENCE_LAYER=1`.

```
raven_ai_agent/patterns/
├── __init__.py            # public exports
├── reflection.py          # Ch. 4 - producer/critic loop
├── planner.py             # Ch. 6 - JSON plan decomposition
├── coordinator.py         # Ch. 7 - semantic multi-agent routing
├── goal_loop.py           # Ch. 11 - goal + criteria iteration
├── fallback.py            # Ch. 12 - graceful degradation chain
├── rag_retriever.py       # Ch. 14 - retrieve-and-ground answers
├── guardrails.py          # Ch. 18 - pre-mutation safety rules
├── intelligence.py        # IntelligenceLayer façade used by agent_v2
└── tests/
    └── test_patterns_smoke.py  # FakeProvider control-flow tests
```

## How the layer plugs into `RaymondLucyAgentV2`

`agent_v2.py` instantiates an `IntelligenceLayer` only when the layer is enabled.
During `process_query`, the agent now consults the layer at four points:

| Stage | Pattern | Trigger |
| --- | --- | --- |
| 1. Pre-LLM classify | `IntelligenceLayer.classify_complexity` | every query (rule-based, free) |
| 2. RAG short-circuit | `RAGRetriever` over `MemoryMixin` | `complexity = rag` |
| 3. Plan injection | `Planner` | `complexity = planning` |
| 4. Post-LLM critic | `ReflectionLoop` | autonomy ≥ 2 and complexity ≠ simple |

If the layer is disabled or any step throws, the original V2 flow runs unchanged.

### Mapping to existing Raven concepts

| Existing module | Pattern that augments it |
| --- | --- |
| `api/multi_agent_router.py` (regex routing) | `Coordinator` semantic fallback (`semantic_route`) |
| `api/memory_manager.py` + `utils/vector_store.py` | `RAGRetriever` |
| `api/intent_resolver.py` (NL → command) | `Planner` (NL → ordered command list) |
| `agents/task_validator.py` (Raymond anti-hallucination) | `GoalLoop` with deterministic checker |
| Provider settings `default_provider` / `fallback_provider` | `FallbackChain` over all five providers |
| Autonomy slider (Copilot / Command / Agent) | `Guardrails` enforcement |

## Pattern reference

### 1. Reflection (Chapter 4)
Producer drafts → critic evaluates against criteria → producer revises.
Bounded by `max_iterations`. Use for BOM creation, pipeline diagnosis, or any
answer where hallucinated IDs are dangerous.

```python
from raven_ai_agent.patterns import ReflectionLoop
loop = ReflectionLoop(provider, producer_system_prompt="You are Raymond-Lucy ...")
res = loop.run("Create BOM for 0307 with 3 sublevels",
               criteria=["item_code must exist", "no negative qty"])
print(res.final_answer, res.accepted, res.iterations)
```

### 2. Planning (Chapter 6)
Returns a strict JSON `Plan` with ordered `PlanStep` objects whose `command`
field can be fed straight into `command_router`.  Used to surface a backbone
for multi-step requests like *"Take SAL-QTN-0901 to a paid invoice"*.

### 3. Coordinator (Chapter 7)
LLM picks one specialist agent from an `AgentSpec` registry and rewrites the
request as a focused instruction.  Wired into `multi_agent_router` as
`semantic_route(command, provider)` for second-chance routing when regex
patterns miss.

### 4. Goal Loop (Chapter 11)
Same shape as Reflection but driven by **explicit success criteria**, and
optionally by a **deterministic checker callable** instead of an LLM judge.
Pair with ERPNext queries (doc-exists, totals match, CFDI fields present).

```python
def my_checker(answer):
    if "SO-00752" not in answer: return GoalCheck(False, ["mention SO-00752"])
    return GoalCheck(True)

loop = GoalLoop(provider, attempt_system_prompt="...",
                external_checker=my_checker, max_iterations=4)
```

### 5. Fallback (Chapter 12)
Generic chain over callables; ships with `provider_chain()` to fall through
your configured providers in order.  Logs latency per attempt.

### 6. RAG Retriever (Chapter 14)
Wraps any retriever callable that returns `[{content, source, score?}]`.
Inside Raven we wire it to `MemoryMixin.search_memories`, so vector hits and
keyword fallback both flow through the same grounding prompt with `[#n]`
citations.

### 7. Guardrails (Chapter 18)
Pre-mutation rulebook that ships with five Raven-specific defaults:

| Rule | Severity |
| --- | --- |
| `submit_requires_target` | High |
| `payment_currency_match` | High |
| `quotation_so_field_match` | High |
| `bulk_requires_ack` (≥ 25 docs) | Medium |
| `copilot_blocks_mutation` | High |

Register custom rules with `Guardrails().register(my_rule)`.  When autonomy is
`agent`, a High violation raises `GuardrailBlocked`.

## Enabling

1. Add a checkbox **Intelligence Layer Enabled** to `AI Agent Settings`
   *(field name: `intelligence_layer_enabled`)*, **or** export
   `RAVEN_INTELLIGENCE_LAYER=1` in the bench environment.
2. Restart the worker.  Logs will show
   `[AI Agent V2] IntelligenceLayer activated`.
3. New `context_used` keys in agent responses: `complexity`, `plan_preview`,
   `reflection_accepted`, and `pattern: rag` for retrieval-grounded replies.

## Tests

```bash
cd raven_ai_agent
python -m raven_ai_agent.patterns.tests.test_patterns_smoke
```

The smoke suite uses a scripted `FakeProvider` so it runs without ERPNext, API
keys, or network access.

## Source attribution

Patterns are adapted from
[evoiz/Agentic-Design-Patterns](https://github.com/evoiz/Agentic-Design-Patterns)
by Antonio Gulli (royalties to Save the Children).  The book is the canonical
reference; this module is the Frappe/ERPNext-flavoured implementation.
