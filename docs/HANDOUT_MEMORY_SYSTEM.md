# 🤖 Raymond-Lucy Memory System - Handout
## ERPNext AI Agent - Memory Enhancement Project

---

## 📊 Current Status (as of March 2026)

### What's Done ✅

| Feature | Status | Notes |
|---------|--------|-------|
| **Importance Scoring** | ✅ Complete | Auto-analyzes content, extracts entities/topics |
| **Consolidation Agent** | ✅ Complete | Timer-based (30 min), finds connections |
| **Citations** | ✅ Complete | Returns source citations |
| **PDF Extraction** | ✅ Complete | Uses PyMuPDF for PO extraction |
| **Custom Fields** | ✅ Complete | Auto-created on app install |
| **PO Automation** | ✅ Complete | Extracts PDF from Sales Order attachments |

---

## 🎯 Next Steps - Session Prompt

### 1. Test PO Extraction Flow
```python
# Manual trigger
from raven_ai_agent.api.po_extractor import manual_extract
result = manual_extract("SO-118026-Calipso s.r.l")
```

### 2. Enable Auto-Trigger (Hooks)
Currently PDF extraction is manual. To enable automatic extraction when PDF is attached:
- The hooks are configured in `hooks.py`
- Needs `bench restart` to activate

### 3. Raven Channel Integration
Create workflow in Raven:
1. User attaches PDF to Sales Order
2. AI detects attachment → extracts PO data
3. AI validates against SO items
4. AI responds in Raven with results

### 4. Consolidation Scheduler
Enable automatic memory consolidation:
```python
from raven_ai_agent.api.consolidation_scheduler import setup_consolidation_scheduler
setup_consolidation_scheduler()
```

---

## 🔬 Comparison: Raymond-Lucy vs Google Always-On Memory

| Feature | Our System | Google System | Gap |
|---------|-----------|--------------|-----|
| Timer consolidation | ✅ New | ✅ | - |
| Cross-memory links | ✅ New | ✅ | - |
| Importance scoring | ✅ New | ✅ | - |
| Multimodal (PDF) | ✅ New | ✅ | - |
| Self-citation | ✅ New | ✅ | - |
| SQLite storage | ❌ | ✅ | Medium |
| Cost monitoring | ✅ | ❌ | We have advantage |

---

## 📁 Key Files

| File | Purpose |
|------|---------|
| `memory_manager.py` | Core memory operations |
| `consolidation_agent.py` | Timer-based memory consolidation |
| `multimodal_ingest.py` | PDF/Image extraction |
| `po_extractor.py` | Sales Order PO extraction |
| `enhanced_search.py` | Relevance scoring search |
| `custom_fields.py` | Auto-create custom fields |

---

## 🚀 Quick Start Commands

```bash
# Pull latest
cd ~/frappe-bench/apps/raven_ai_agent
git pull upstream main
bench restart

# Create custom fields
bench console --site [site]
from raven_ai_agent.api.custom_fields import create_po_extraction_fields
create_po_extraction_fields()

# Test PO extraction
from raven_ai_agent.api.po_extractor import manual_extract
result = manual_extract("SO-XXXXX-Customer")

# Enable consolidation
from raven_ai_agent.api.consolidation_scheduler import setup_consolidation_scheduler
setup_consolidation_scheduler()
```

---

## 📋 Questions for Next Session

1. [ ] Is PO extraction working for all PDF types?
2. [ ] Should we enable auto-trigger on file attachment?
3. [ ] Do we need validation logic (compare PDF items vs SO items)?
4. [ ] Enable consolidation scheduler?
5. [ ] Raven channel workflow - how should AI respond?

---

*Handout prepared: March 2026*
*raven_ai_agent: https://github.com/rogerboy38/raven_ai_agent*
