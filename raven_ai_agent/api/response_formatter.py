"""
Response Formatter Utility
==========================

Provides consistent formatting for all AI agent responses.
Uses markdown tables and structured output for human-readable results.

Usage:
    from raven_ai_agent.api.response_formatter import format_response, format_table
    
    # Format a simple response
    formatted = format_response("Your message here")
    
    # Format a list as a table
    formatted = format_table(data, columns=["Name", "Status", "Amount"])
"""

import frappe
import re
from typing import Dict, List, Any, Optional


def format_response(response: str, format_type: str = "auto") -> str:
    """
    Apply consistent formatting to AI responses.
    
    Args:
        response: The raw response text
        format_type: Auto-detect or force a specific format
        
    Returns:
        Formatted response string
    """
    if not response:
        return response
    
    # Don't format if already formatted (contains markdown tables)
    if "|" in response and response.count("|") > 5:
        return response
    
    # Apply formatting based on content type
    response = _format_lists(response)
    response = _format_key_value(response)
    response = _format_documents(response)
    response = _format_summary(response)
    
    return response


def _format_lists(text: str) -> str:
    """Format bullet points and numbered lists consistently"""
    # Convert various bullet formats to consistent markdown
    lines = text.split('\n')
    formatted_lines = []
    
    for line in lines:
        # Skip empty lines but preserve paragraph breaks
        if not line.strip():
            formatted_lines.append('')
            continue
        
        # Convert • to - for consistency
        if '•' in line:
            line = line.replace('•', '-')
        
        # Ensure list items have proper spacing
        if line.strip().startswith(('-', '*', '1.')):
            # Add emoji indicators based on content
            if '✅' not in line and '❌' not in line:
                if 'success' in line.lower() or 'complete' in line.lower() or 'done' in line.lower():
                    line = line.replace('- ', '- ✅ ', 1)
                elif 'fail' in line.lower() or 'error' in line.lower() or 'issue' in line.lower():
                    line = line.replace('- ', '- ❌ ', 1)
        
        formatted_lines.append(line)
    
    return '\n'.join(formatted_lines)


def _format_key_value(text: str) -> str:
    """Format key-value pairs into clean structure"""
    # Pattern: "Key: Value" or "Key - Value"
    lines = text.split('\n')
    formatted_lines = []
    in_table = False
    
    for line in lines:
        # Check for key-value patterns
        kv_match = re.match(r'^\s*([^:]+)[:\-]\s*(.+)$', line)
        
        if kv_match and len(line) < 80:  # Only short key-value pairs
            key = kv_match.group(1).strip()
            value = kv_match.group(2).strip()
            
            # Don't convert if already in a list or code block
            if not any(x in line for x in ['`', '|', '**']):
                # Format as bold key
                line = f"**{key}:** {value}"
        
        formatted_lines.append(line)
    
    return '\n'.join(formatted_lines)


def _format_documents(text: str) -> str:
    """Format document references consistently"""
    # Pattern: DocType-XXXXX format
    doctype_pattern = r'\b(SO|ACC-SINV|ACC-PAY|ACC-DN|SAL-QTN|MFG-WO|BOM|Batch)-\d+[-[\w\.]*]*\b'
    
    def replace_doc(match):
        doc_id = match.group(0)
        return f"`{doc_id}`"
    
    return re.sub(doctype_pattern, replace_doc, text)


def _format_summary(text: str) -> str:
    """Add visual separation for summary sections"""
    # Add separators before summary lines
    lines = text.split('\n')
    formatted_lines = []
    
    for i, line in enumerate(lines):
        # Check for summary keywords
        lower = line.lower()
        if any(kw in lower for kw in ['summary', 'total:', 'overall:', 'result:']):
            if i > 0 and lines[i-1].strip():
                formatted_lines.append('---')
        
        formatted_lines.append(line)
    
    return '\n'.join(formatted_lines)


def format_table(data: List[Dict], columns: List[str], title: str = None) -> str:
    """
    Format a list of dictionaries as a markdown table.
    
    Args:
        data: List of dictionaries
        columns: Column names to include
        title: Optional table title
        
    Returns:
        Formatted markdown table
    """
    if not data:
        return "No data available."
    
    lines = []
    
    # Add title if provided
    if title:
        lines.append(f"### {title}\n")
    
    # Header row
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---" for _ in columns]) + " |"
    
    lines.append(header)
    lines.append(separator)
    
    # Data rows
    for row in data:
        values = []
        for col in columns:
            value = row.get(col, "")
            # Truncate long values
            if isinstance(value, str) and len(str(value)) > 50:
                value = str(value)[:47] + "..."
            values.append(str(value))
        
        row_str = "| " + " | ".join(values) + " |"
        lines.append(row_str)
    
    return "\n".join(lines)


def format_issues(issues: List[Dict], title: str = "Issues Found") -> str:
    """Format a list of issues as a structured markdown table"""
    if not issues:
        return f"✅ No {title.lower()} found."
    
    lines = []
    
    if title:
        lines.append(f"### {title}\n")
    
    # Group by severity
    severity_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
    grouped = {}
    
    for issue in issues:
        severity = issue.get("severity", "INFO")
        if severity not in grouped:
            grouped[severity] = []
        grouped[severity].append(issue)
    
    # Output by severity
    for severity in severity_order:
        if severity not in grouped:
            continue
        
        severity_emoji = {
            "CRITICAL": "🔴",
            "HIGH": "🟠", 
            "MEDIUM": "🟡",
            "LOW": "⚪",
            "INFO": "ℹ️"
        }.get(severity, "•")
        
        lines.append(f"\n#### {severity_emoji} {severity} ({len(grouped[severity])})\n")
        
        for issue in grouped[severity]:
            msg = issue.get("message", "")
            field = issue.get("field", "")
            auto_fix = issue.get("auto_fix", "")
            
            lines.append(f"- **{msg}**")
            if field:
                lines.append(f"  - Field: `{field}`")
            if auto_fix:
                fix_val = issue.get("auto_fix_value", "")
                conf = issue.get("fix_confidence", 0)
                if fix_val:
                    lines.append(f"  - Fix: `{auto_fix}` → `{fix_val}` ({conf*100:.0f}% confidence)")
                else:
                    lines.append(f"  - Fix: `{auto_fix}` ({conf*100:.0f}% confidence)")
            lines.append("")
    
    return "\n".join(lines)


def format_document_status(doc_name: str, doc_type: str, status: str, details: Dict = None) -> str:
    """Format a document status as a compact card"""
    status_emoji = {
        "Draft": "📝",
        "Submitted": "✅", 
        "Cancelled": "❌",
        "Completed": "🎉",
        "Partial": "⚠️"
    }.get(status, "📋")
    
    lines = [
        f"### {status_emoji} {doc_type}: `{doc_name}`",
        f"**Status:** {status}",
        ""
    ]
    
    if details:
        for key, value in details.items():
            if value:
                lines.append(f"- **{key}:** `{value}`")
    
    return "\n".join(lines)


def format_confidence_score(confidence: float, label: str = "Confidence") -> str:
    """Format a confidence score with visual indicator"""
    if confidence >= 0.9:
        emoji = "🟢"
        text = "HIGH"
    elif confidence >= 0.7:
        emoji = "🟡"
        text = "MEDIUM"
    else:
        emoji = "🔴"
        text = "LOW"
    
    return f"{emoji} **{label}:** {text} ({confidence*100:.0f}%)"


def format_action_result(action: str, success: bool, details: str = None) -> str:
    """Format an action result with consistent styling"""
    if success:
        emoji = "✅"
        lines = [f"{emoji} **{action}** completed successfully"]
    else:
        emoji = "❌"
        lines = [f"{emoji} **{action}** failed"]
    
    if details:
        lines.append(f"   {details}")
    
    return "\n".join(lines)


def apply_post_processing(response: str, context: Dict = None) -> str:
    """
    Main post-processing function - applies all formatting to a response.
    
    This is the main entry point that should be called before sending
    any response to the user.
    
    Args:
        response: The raw response text
        context: Optional context about the request (doc_type, action, etc.)
        
    Returns:
        Fully formatted response
    """
    if not response:
        return response
    
    # Skip if already contains advanced markdown
    if response.count("```") >= 2:  # Has code blocks
        return response
    
    # Apply base formatting
    response = format_response(response)
    
    # Add visual polish
    response = _add_visual_polish(response)
    
    return response


def _add_visual_polish(text: str) -> str:
    """Add final visual touches"""
    lines = text.split('\n')
    polished = []
    
    for i, line in enumerate(lines):
        # Add spacing before headers
        if line.startswith('###') or line.startswith('##'):
            if i > 0 and lines[i-1].strip():
                polished.append('')  # Add blank line before headers
        
        polished.append(line)
        
        # Add spacing after headers
        if line.startswith('##'):
            polished.append('')
    
    # Clean up multiple blank lines
    result = '\n'.join(polished)
    while '\n\n\n' in result:
        result = result.replace('\n\n\n', '\n\n')
    
    return result
