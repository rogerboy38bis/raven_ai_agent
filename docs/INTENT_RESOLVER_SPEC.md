# Intent Resolver Specification

This document describes the Natural Language Intent Resolution system that converts user natural language queries into documented command formats.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Command Catalog](#command-catalog)
3. [Intent Resolution Flow](#intent-resolution-flow)
4. [Entity Extraction](#entity-extraction)
5. [Confidence Scoring](#confidence-scoring)
6. [Integration](#integration)
7. [Adding New Intents](#adding-new-intents)

---

## Architecture Overview

### Problem Statement

The current system uses keyword/regex matching in `command_router.py`. When users type natural language like:

- "what is the status of my order for Calipso?"
- "convert the quotation for ALBAAD to a sales order"
- "check on my pending invoices"

The keyword matching may fail or route incorrectly because the keywords don't match exactly.

### Solution: Hybrid Approach

```
User: "@ai what is the status of my order for Calipso?"
           │
           ▼
┌──────────────────────────────┐
│   intent_resolver.py         │
│                              │
│  1. Fast regex pre-check    │
│     (already a command?)     │
│                              │
│  2. Cache lookup            │
│     (seen this before?)      │
│                              │
│  3. LLM classification      │
│     (or fallback rules)     │
│                              │
└──────────────────────────────┘
           │
           ▼ (if confidence >= 0.7)
┌──────────────────────────────┐
│   command_router.py          │
│   (UNCHANGED)               │
│                              │
│  diagnose SAL-ORD-2024-00754│
└──────────────────────────────┘
```

### Key Features

1. **Fast Path**: Direct command patterns bypass LLM for performance
2. **LLM Classification**: Natural language → documented commands
3. **Fallback Rules**: Rule-based when LLM unavailable
4. **Caching**: Identical queries cached for 1 hour
5. **Graceful Degradation**: Falls through to existing router if resolution fails

---

## Command Catalog

The command catalog maps intents to command templates. Each intent can have multiple command formats.

### Current Intents

| Intent | Command Templates | Example |
|--------|------------------|---------|
| `status_check` | `diagnose {document_id}`, `status {doc_type} {doc_id}` | `diagnose SAL-ORD-2024-00754` |
| `pipeline_diagnosis` | `diagnose {quotation_id}`, `validate pipeline {quotation_id}` | `diagnose SAL-QTN-2024-00760` |
| `create_sales_order` | `convert quotation {qtn_id} to sales order` | `convert quotation SAL-QTN-2024-00760 to sales order` |
| `submit_sales_order` | `!submit sales order {so_id}` | `!submit sales order SAL-ORD-2024-00123` |
| `sales_order_to_work_order` | `create work order from {so_id}` | `create work order from SAL-ORD-2024-00123` |
| `sales_order_to_delivery` | `delivery from {so_id}` | `delivery from SAL-ORD-2024-00123` |
| `sales_order_to_invoice` | `invoice from {so_id}` | `invoice from SAL-ORD-2024-00123` |
| `submit_quotation` | `submit quotation {qtn_id}`, `!submit quotation {qtn_id}` | `!submit quotation SAL-QTN-2024-00760` |
| `create_payment_entry` | `create payment for {sinv_id}`, `payment for {sinv_id}` | `create payment for SINV-2024-00500` |
| `get_unpaid_invoices` | `overdue invoices`, `unpaid invoices` | `overdue invoices` |
| `create_bom` | `create bom for batch {batch_id}` | `create bom for batch LOTE-2024-00123` |
| `stock_entry_work_order` | `stock entry for {wo_id}`, `material transfer {wo_id}` | `stock entry for MFG-WO-2024-00123` |
| `sensor_status` | `sensor status {bot_id}`, `sensor {bot_id}` | `sensor status BOT-001` |
| `temperature_check` | `temperature {bot_id}`, `check temperature {bot_id}` | `temperature BOT-001` |
| `help` | `help`, `show help` | `help` |

### Adding New Commands

To add a new command to the catalog:

1. Add intent name to `COMMAND_CATALOG` in `intent_resolver.py`
2. Add command templates (use `{entity}` placeholders)
3. Update the LLM prompt with new commands
4. Add tests

```python
# Example: Adding new intent
COMMAND_CATALOG = {
    # ... existing intents ...
    
    "my_new_intent": [
        "do action {item}",
        "perform {action} on {item}",
    ],
}
```

---

## Intent Resolution Flow

### Step 1: Fast Pre-Check

The system first checks if the input is already a documented command:

```python
def is_direct_command(self, raw_text: str) -> bool:
    """Fast pre-check for direct command patterns"""
    for pattern in DIRECT_COMMAND_PATTERNS:
        if re.search(pattern, raw_text, re.IGNORECASE):
            return True
    return False
```

**Direct Command Patterns** include:
- Document IDs: `SAL-QTN-XXXX`, `SO-XXX`, `SINV-XXXX`, etc.
- Command keywords: `diagnose`, `status`, `!submit`, `convert`, `help`
- `@ai` prefix

### Step 2: Cache Lookup

If not a direct command, check cache:

```python
cache_key = f"intent_resolve:{raw_text.strip().lower()}"
cached = frappe.cache().get_value(cache_key)
if cached:
    return json.loads(cached)
```

Cached results expire after 1 hour.

### Step 3: LLM Classification

If not cached, call LLM with structured prompt:

```python
prompt = f"""You are an intent classifier...

AVAILABLE COMMANDS:
{catalog_text}

USER MESSAGE: "{raw_text}"

Return JSON:
{{
    "intent": "...", 
    "entities": {{...}}, 
    "resolved_command": "...", 
    "confidence": 0.0-1.0
}}
"""
```

### Step 4: Fallback Rules

If LLM fails, use rule-based fallback:

```python
def _fallback_resolution(self, prompt: str) -> str:
    """Simple rule-based when LLM unavailable"""
    text = extract_user_message(prompt)
    
    # Keyword matching
    if "status" in text.lower():
        doc_id = extract_document_id(text)
        if doc_id:
            return f"diagnose {doc_id}"
    
    # ... more rules
```

---

## Entity Extraction

### Document ID Extraction

Extracts document IDs using regex patterns:

```python
DOCUMENT_ID_PATTERNS = [
    r'SAL-QTN-\d+-\d+',     # Quotations: SAL-QTN-2024-00760
    r'SAL-ORD-\d+-\d+',      # Sales Orders: SAL-ORD-2024-00123
    r'SO-\d{3,5}',           # Short SO: SO-00754
    r'SINV-\d+-\d+',         # Sales Invoices: SINV-2024-00500
    r'DN-\d+-\d+',           # Delivery Notes: DN-2024-00123
    r'MFG-WO-\d+',           # Work Orders: MFG-WO-2024-00123
    r'LOTE-\d+',             # Batches: LOTE-2024-00123
    r'BOM-[^\s]+',           # BOMs: BOM-ITEM-001
]
```

### Customer Name Extraction

Fuzzy matches customer names against database:

```python
def extract_customer_name(self, text: str) -> Optional[str]:
    # Extract potential name from text
    patterns = [
        r'for\s+([A-Za-z\s]+?)(?:\s+for|\s+order|\s+invoice|$)',
        r'customer\s+([A-Za-z\s]+?)(?:\s+order|\s+invoice|$)',
    ]
    
    # Query Frappe Customer doctype
    customers = frappe.db.get_all(
        "Customer",
        filters={"name": ["like", f"%{customer_name}%"]},
        fields=["name", "customer_name"]
    )
    
    return customers[0].name if customers else None
```

### Item Code Extraction

Fuzzy matches item codes:

```python
def extract_item_code(self, text: str) -> Optional[str]:
    patterns = [
        r'item\s+([A-Za-z0-9-]+)',
        r'product\s+([A-Za-z0-9-]+)',
    ]
    
    # Query Frappe Item doctype
    items = frappe.db.get_all(
        "Item",
        filters={"name": ["like", f"%{item_code}%"]},
        fields=["name", "item_code"]
    )
    
    return items[0].name if items else None
```

---

## Confidence Scoring

### LLM Confidence

The LLM returns a confidence score (0.0 - 1.0):

| Confidence | Action |
|------------|--------|
| >= 0.7 | Use resolved command |
| 0.6 - 0.69 | Filtered out, use fallback router |
| < 0.6 | Return `null` (unknown intent) |

### Threshold Logic

```python
# In resolve_intent_message (router integration)
if result and result.get("resolved_command"):
    confidence = result.get("confidence", 0)
    if confidence >= 0.7:
        return result["resolved_command"]  # Use resolved
    else:
        return None  # Fall through to router
```

### Confidence Factors

The LLM considers:
1. **Keyword match clarity** - How clear are the intent keywords?
2. **Entity extraction** - Were required entities found?
3. **Context clues** - Does the query fit a known pattern?

---

## Integration

### Router Integration

In `router.py`, the intent resolver is called after `@ai` detection:

```python
# Check for @ai trigger
if plain_text.lower().startswith("@ai"):
    query = plain_text[3:].strip()
    
    # Phase 7: Try intent resolution
    resolved_command = None
    try:
        from raven_ai_agent.api.intent_resolver import resolve_intent_message
        resolved_command = resolve_intent_message(query)
        if resolved_command:
            frappe.logger().info(f"[IntentResolver] Using resolved command: {resolved_command}")
            query = resolved_command
    except Exception as e:
        frappe.logger().warning(f"[IntentResolver] Resolution failed: {e}")
    
    bot_name = _detect_ai_intent(query)
```

### Whitelist API

The resolver exposes a whitelist function:

```python
@frappe.whitelist()
def resolve_intent_message(message: str) -> Optional[str]:
    """Returns resolved command if confidence >= 0.7, else None"""
    resolver = IntentResolver()
    result = resolver.resolve_intent(message)
    
    if result and result.get("resolved_command"):
        if result.get("confidence", 0) >= 0.7:
            return result["resolved_command"]
    
    return None
```

### Flow Summary

```
User message
    │
    ▼
@ai detected in router.py
    │
    ▼
resolve_intent_message()
    │
    ├──▶ Direct command? → return None (router handles)
    │
    ├──▶ Cache hit? → return cached result
    │
    ├──▶ LLM call → get intent + entities
    │       │
    │       └──▶ confidence >= 0.7? → return resolved command
    │       │
    │       └──▶ confidence < 0.7? → return None (router handles)
    │
    └──▶ LLM fails? → return None (router handles)
    
Resolved command passed to _detect_ai_intent()
    │
    ▼
Existing command_router.py (UNCHANGED)
```

---

## Adding New Intents

### Step 1: Add to Command Catalog

Edit `raven_ai_agent/api/intent_resolver.py`:

```python
COMMAND_CATALOG = {
    # ... existing ...
    
    "my_new_intent": [
        "command template {entity1}",
        "alternate {entity1} {entity2}",
    ],
}
```

### Step 2: Add Direct Command Pattern (Optional)

If the command can be typed directly, add to `DIRECT_COMMAND_PATTERNS`:

```python
DIRECT_COMMAND_PATTERNS = [
    # ... existing ...
    r'^my_command\s+',
]
```

### Step 3: Add Tests

Add test cases in `tests/test_intent_resolver.py`:

```python
def test_my_new_intent(self):
    """Test my new intent resolution"""
    # ... test code ...
```

### Step 4: Update Documentation

Update this specification document with the new intent.

---

## Configuration

### Confidence Thresholds

| Threshold | Value | Purpose |
|-----------|-------|---------|
| Filter threshold | 0.6 | LLM filters out low-confidence responses |
| Use threshold | 0.7 | Router uses resolved command |

### Cache TTL

```python
frappe.cache().set_value(cache_key, result, expires_in=3600)  # 1 hour
```

### LLM Configuration

Uses existing LLM configuration from Frappe settings:

```python
settings = frappe.get_doc("Raven AI Settings")
provider = settings.get("default_provider", "openai")
```

---

## Monitoring & Logging

### Log Levels

```python
# Resolution success
frappe.logger().info(f"[IntentResolver] \"{raw}\" -> \"{resolved}\" (conf={confidence})")

# Cache hit
frappe.logger().info(f"[IntentResolver] Cache hit: {raw_text}")

# Resolution failure (continues to router)
frappe.logger().warning(f"[IntentResolver] Resolution failed: {e}")
```

### Metrics to Track

1. **Resolution rate**: % of queries resolved
2. **Confidence distribution**: Average confidence score
3. **Cache hit rate**: % from cache
4. **Fallback rate**: % using rule-based fallback

---

## Error Handling

### Graceful Degradation

If intent resolution fails at any step, the system falls through to the existing keyword router:

1. **Direct command check fails** → Continue to router
2. **Cache lookup fails** → Continue to LLM
3. **LLM call fails** → Use fallback rules
4. **Fallback fails** → Continue to router
5. **Router fails** → Return error to user

### No Breaking Changes

The intent resolver is **optional**:
- If disabled → router works as before
- If LLM unavailable → fallback to rules
- If resolution fails → router handles it
- If confidence low → router handles it

---

## Example Conversations

### Example 1: Status Check

**User Input:**
```
@ai what is the status of my order for Calipso?
```

**Resolution:**
- Intent: `status_check`
- Entities: `{"document_id": "SAL-ORD-2024-00754", "customer_name": "Calipso"}`
- Resolved: `diagnose SAL-ORD-2024-00754`
- Confidence: 0.85

**Router receives:** `diagnose SAL-ORD-2024-00754`

### Example 2: Create Sales Order

**User Input:**
```
@ai convert the quotation for ALBAAD to a sales order
```

**Resolution:**
- Intent: `create_sales_order`
- Entities: `{"document_id": "SAL-QTN-2024-00760", "customer_name": "ALBAAD"}`
- Resolved: `convert quotation SAL-QTN-2024-00760 to sales order`
- Confidence: 0.88

**Router receives:** `convert quotation SAL-QTN-2024-00760 to sales order`

### Example 3: Unknown Intent

**User Input:**
```
@ai hello how are you today?
```

**Resolution:**
- Intent: `null`
- Confidence: 0.1 (below threshold)
- Resolved: `null`

**Router receives:** Original message (router will not match, returns help)

---

## Testing

### Unit Tests

Run intent resolver tests:

```bash
python -m pytest tests/test_intent_resolver.py -v
```

### Integration Tests

Test end-to-end flow:

```python
# Test natural language resolution
result = resolve_intent_message("what is the status of my order?")
assert result == "diagnose SAL-ORD-2024-XXXXX"

# Test fallback
result = resolve_intent_message("unknown command xyz")
assert result is None  # Falls through to router
```

---

*Last Updated: 2024-01-15*
*Version: 1.0*
*Maintainer: Development Team*
