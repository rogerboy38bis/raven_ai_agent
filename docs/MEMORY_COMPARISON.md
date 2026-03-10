# Memory Systems Comparison

## Raymond-Lucy Protocol (raven_ai_agent) vs Google Always-On Memory Agent

---

## Overview

| System | Architecture | Storage | Primary Use |
|--------|-------------|---------|-------------|
| **Raymond-Lucy** | Frappe-native | Frappe DocType + VectorDB | ERPNext/Raven integration |
| **Google Always-On** | ADK + SQLite | SQLite only | Standalone AI assistant |

---

## Feature Comparison

| Feature | Raymond-Lucy | Google Always-On |
|---------|--------------|------------------|
| **Memory Storage** | Frappe DocType (`AI Memory`) | SQLite (`memory.db`) |
| **Vector Embeddings** | ✅ Optional (VectorStore) | ❌ Not required |
| **Importance Scoring** | ⚠️ Manual + Auto (new) | ✅ Auto (0-1) |
| **Entity Extraction** | ⚠️ Basic (new) | ✅ Full NER |
| **Topic Extraction** | ⚠️ Basic (new) | ✅ Full topic modeling |
| **Consolidation** | ⚠️ Basic (new) | ✅ Timer-based (30 min) |
| **Cross-Memory Links** | ⚠️ Basic (new) | ✅ Automatic |
| **Session Summary** | ✅ Lucy Protocol | ❌ |
| **Morning Briefing** | ✅ Lucy Protocol | ❌ |
| **ERPNext Integration** | ✅ Native | ❌ |
| **Permission-Aware** | ✅ Frappe permissions | ❌ |
| **Multimodal Ingest** | ❌ | ✅ (27 file types) |
| **Self-Citation** | ⚠️ Basic (new) | ✅ Full citations |
| **Cost Monitoring** | ✅ Built-in | ❌ |

---

## Protocol Mapping

### Raymond Protocol (Anti-Hallucination)

| Aspect | Implementation |
|--------|----------------|
| **Verified Data** | `context_builder.py` - queries ERPNext with permissions |
| **Source Tracking** | `source` field in AI Memory |
| **Verification Flag** | `verified` checkbox |

### Lucy Protocol (Context Continuity)

| Aspect | Implementation |
|--------|----------------|
| **Session Start** | `get_morning_briefing()` - loads high-priority memories |
| **Session End** | `end_session()` - generates summary |
| **Summary Storage** | `memory_type: "Summary"` |

### Memento Protocol (Persistent Memory)

| Aspect | Implementation |
|--------|----------------|
| **Storage** | `tattoo_fact()` - stores to AI Memory |
| **Retrieval** | `search_memories()` - RAG-style search |
| **Types** | Fact, Preference, Summary, Correction, Interaction, Sensor Alert |

### Karpathy Protocol (Autonomy Slider)

| Level | Name | Implementation |
|-------|------|----------------|
| 1 | Copilot | Read-only queries |
| 2 | Command | Execute with confirmation |
| 3 | Agent | Multi-step autonomous workflows |

---

## New Enhancements (Post-Comparison)

### Phase 1: Auto Importance Scoring

```python
# New: Auto-analyze when storing
doc = frappe.get_doc({
    "doctype": "AI Memory",
    "importance_score": 0.85,  # Auto-calculated
    "entities": "John, Project X",  # Auto-extracted
    "topics": "manufacturing, quality"  # Auto-extracted
})
```

### Phase 2: Consolidation Agent

- Runs every 30 minutes (configurable)
- Finds connections between memories
- Generates cross-cutting insights
- Compresses redundant information

### Phase 3: Citations

```python
# Search now returns citations
{
    "content": "User prefers email communication",
    "citation": "[Conversation (2026-03-09), High (80%)]"
}
```

---

## Architecture Diagrams

### Raymond-Lucy Flow

```
User Message
    ↓
[Agent] → [Context Builder] → ERPNext Data
    ↓
[Memory Manager] → Search AI Memory
    ↓
[Response] + [Optional: tattoo_fact()]
    ↓
Session End → [Consolidation Agent] → Insights
```

### Google Always-On Flow

```
Input (File/API)
    ↓
[IngestAgent] → Extract entities, topics, importance
    ↓
[SQLite Store]
    ↓
[ConsolidateAgent] (timer) → Find connections
    ↓
[QueryAgent] → Retrieve + Cite
```

---

## Recommendations

### Short Term (This Sprint)
1. ✅ Importance scoring - **DONE**
2. ✅ Consolidation agent - **DONE**
3. ✅ Citations - **DONE**

### Medium Term (Next Sprint)
- Add multimodal ingest support
- Enhance entity extraction with proper NER
- Add scheduled job for consolidation

### Long Term
- Consider SQLite for raw storage (faster queries)
- Add cost monitoring to consolidation
- Implement what-if scenarios for memory analysis

---

## Sources

- Google Always-On Memory: https://github.com/GoogleCloudPlatform/generative-ai/tree/main/gemini/agents/always-on-memory-agent
- raven_ai_agent: https://github.com/rogerboy38/raven_ai_agent

---

*Last updated: 2026-03-10*
*Project: Memory Enhancement Phase 1-3*
