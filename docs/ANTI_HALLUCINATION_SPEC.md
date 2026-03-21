# Anti-Hallucination Guard - Specification

## Overview

Phase 8A introduces an Anti-Hallucination Guard that validates LLM responses against real ERPNext data before sending them to users. This ensures the bot only provides accurate, verified information.

## Architecture

### Pipeline Flow

```
User Query → Agent → LLM → validate_and_sanitize() → User Response
                    ↑           ↓
                    └─ context_data (ERPNext)
```

1. **Query Processing**: Agent receives user query
2. **Context Building**: Real ERPNext data is gathered from the system
3. **LLM Generation**: LLM generates response based on context
4. **Validation**: Response is validated against real data
5. **Sanitization**: Placeholders and hallucinations are removed
6. **Response**: Final validated response sent to user

## Components

### truth_hierarchy.py - Validation Functions

#### `extract_numeric_values(text: str) -> List[Dict]`

Extracts all numeric values from text for validation.

**Returns:**
- `List[Dict]` with keys: `value`, `type`, `original`, `position`
- Types: `currency`, `quantity`, `percentage`, `date`, `generic`

#### `validate_response(response_text: str, context_data: Dict) -> Dict`

Validates LLM response against real ERPNext data.

**Context Data Structure:**
```python
{
    "document_type": "Sales Order",
    "document_name": "SO-00754-Calipso",
    "amount": 69189.12,
    "customer": "Calipso s.r.l",
    "status": "Completed",
    "delivery_status": "Fully Delivered",
    "billing_status": "Fully Billed",
    "delivery_date": "2024-01-29",
}
```

**Returns:**
```python
{
    "validated": bool,           # True if response matches context
    "confidence": float,         # 0.0-1.0 confidence score
    "corrections": [             # List of corrections needed
        {
            "type": "amount_mismatch",
            "original": "$50,000",
            "correct": "$69,189.12",
            "explanation": "Response claimed $50,000 but actual is $69,189.12"
        }
    ],
    "issues": [],               # List of issue descriptions
    "validated_values": {}      # Values that were checked and match
}
```

#### `sanitize_response(response_text: str) -> Dict`

Removes hallucinated/placeholder data from response.

**Returns:**
```python
{
    "cleaned": str,           # The sanitized response
    "removed": [],            # List of removed items
    "safe": bool              # True if response is now safe
}
```

**Detected Patterns:**
- `[Placeholder]` text
- `[TODO]`, `[FIXME]`
- `Customer: [Name]`, `Amount: [$X,XXX]`
- Any `[...]` bracket patterns

#### `validate_and_sanitize(response_text: str, context_data: Dict = None) -> Dict`

Main entry point - combines validation and sanitization.

**Returns:**
```python
{
    "original": str,           # Original LLM response
    "sanitized": str,          # After removing placeholders
    "validated": bool,         # Whether validation passed
    "confidence": float,       # 0.0-1.0
    "corrections": [],         # Required corrections
    "safe": bool,             # Whether to send to user
    "final_response": str      # The response to send to user
}
```

## Confidence Thresholds

| Confidence | Action |
|------------|--------|
| ≥ 0.6 | Pass - Response sent as-is |
| 0.3 - 0.6 | Warning - Add disclaimer to response |
| < 0.3 | Fail - Replace with error message |

## Integration in agent.py

The validation is integrated in the `process_query()` method after the LLM generates a response:

```python
# After LLM generates answer
validation_result = validate_and_sanitize(answer, context_data)

# Log validation failures
if not validation_result.get("validated", True):
    frappe.logger().warning(
        f"[Anti-Hallucination] Validation failed. "
        f"Confidence: {validation_result.get('confidence', 0):.2f}"
    )

# Use validated response
answer = validation_result.get("final_response", answer)
```

## Adding New Validation Rules

To add new validation rules, modify `validate_response()` in `truth_hierarchy.py`:

1. **Add new field checks:**
```python
# Example: Add shipping address validation
if "shipping_address" in context_data:
    expected = str(context_data["shipping_address"]).lower()
    if expected not in response_text.lower():
        issues.append(f"Missing shipping address: {expected}")
        confidence -= 0.1
```

2. **Add new pattern detection:**
```python
# Example: Detect specific hallucination patterns
new_patterns = [
    r'(?:serial|lot)\s+number[:\s]+\[.*?\]',
]
for pattern in new_patterns:
    if re.search(pattern, response_text, re.IGNORECASE):
        issues.append(f"Hallucinated field pattern: {pattern}")
        confidence -= 0.1
```

## Testing

Run the anti-hallucination tests:

```bash
pytest tests/test_truth_hierarchy.py -v
```

**Test Categories:**
- `TestExtractNumericValues`: Currency, quantity, percentage, date extraction
- `TestSanitizeResponse`: Placeholder removal
- `TestValidateResponse`: Validation against context data
- `TestValidateAndSanitize`: Full pipeline
- `TestIntegrationWithResponseFormatter`: Integration with response_formatter

## Monitoring

Validation failures are logged with:
- Log level: `WARNING`
- Log source: `raven_ai_agent`
- Log message format: `[Anti-Hallucination] Validation failed for response. Confidence: X.XX`

Check logs with:
```bash
bench console
>>> frappe.logger("raven_ai_agent").warning("test")
```

Or check the Frappe Error Log doctype for production monitoring.

## Future Enhancements

1. **Vector Store Validation**: Cross-check facts against stored memories
2. **Multi-Source Validation**: Validate against multiple ERPNext documents
3. **User Feedback Loop**: Learn from user corrections
4. **Confidence Calibration**: Adjust thresholds based on LLM performance
