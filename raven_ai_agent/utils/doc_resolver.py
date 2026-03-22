"""
Document Name Resolver Utility

Provides functions to resolve partial document names to full names.
Handles cases like:
- "SO-00752" → "SO-00752-LEGOSAN AB"
- "Calipso" → "Calipso s.r.l" (if unique match)
- "QTN-00752" → "QTN-00752-CUSTOMER NAME"

Usage:
    from raven_ai_agent.utils.doc_resolver import resolve_document_name
    
    full_name = resolve_document_name("Sales Order", "SO-00752")
    # Returns "SO-00752-LEGOSAN AB" or raises frappe.DoesNotExistError
"""
import frappe
from typing import Optional, List, Dict


def resolve_document_name(doctype: str, partial_name: str) -> str:
    """
    Resolve a partial document name to the full document name.
    
    Args:
        doctype: The doctype (e.g., "Sales Order", "Quotation", "Customer")
        partial_name: The partial or full name to resolve
        
    Returns:
        The full document name if found
        
    Raises:
        frappe.DoesNotExistError: If no document is found
        frappe.ValidationError: If multiple documents match (ambiguous)
    """
    if not partial_name:
        raise frappe.DoesNotExistError("Document name cannot be empty")
    
    # First try exact match
    try:
        doc = frappe.get_doc(doctype, partial_name)
        return doc.name
    except frappe.DoesNotExistError:
        pass
    except Exception:
        # Other errors (permissions etc), try fuzzy match
        pass
    
    # Try fuzzy match with LIKE
    matches = frappe.get_all(
        doctype,
        filters={"name": ["like", f"%{partial_name}%"]},
        fields=["name"],
        limit=10
    )
    
    if not matches:
        raise frappe.DoesNotExistError(f"{doctype} '{partial_name}' not found")
    
    if len(matches) == 1:
        return matches[0].name
    
    # Multiple matches - check if one is an exact prefix match
    for m in matches:
        if m.name.startswith(partial_name):
            return m.name
    
    # Still ambiguous - raise error with suggestions
    suggestions = ", ".join([m.name for m in matches[:5]])
    raise frappe.ValidationError(
        f"Ambiguous name '{partial_name}'. Did you mean one of: {suggestions}?"
    )


def resolve_document_name_safe(doctype: str, partial_name: str) -> Optional[str]:
    """
    Safe version of resolve_document_name that returns None instead of raising.
    
    Args:
        doctype: The doctype
        partial_name: The partial or full name to resolve
        
    Returns:
        The full document name if found, None otherwise
    """
    try:
        return resolve_document_name(doctype, partial_name)
    except frappe.DoesNotExistError:
        return None
    except frappe.ValidationError:
        return None


def search_documents(doctype: str, query: str, limit: int = 10) -> List[Dict]:
    """
    Search for documents by name or customer/party name.
    
    Args:
        doctype: The doctype to search
        query: Search query
        limit: Maximum results to return
        
    Returns:
        List of matching documents with name and link
    """
    site_name = frappe.local.site
    doctype_slug = doctype.lower().replace(" ", "-")
    
    # Search by name
    by_name = frappe.get_all(
        doctype,
        filters={"name": ["like", f"%{query}%"]},
        fields=["name"],
        limit=limit
    )
    
    results = []
    for r in by_name:
        results.append({
            "name": r.name,
            "link": f"https://{site_name}/app/{doctype_slug}/{r.name}",
            "match_type": "name"
        })
    
    # If we have room, also search by customer/party name
    if len(results) < limit:
        customer_field = None
        if doctype in ["Sales Order", "Quotation", "Sales Invoice"]:
            customer_field = "customer_name"
        elif doctype == "Customer":
            customer_field = "customer_name"
            
        if customer_field:
            meta = frappe.get_meta(doctype)
            if meta.has_field(customer_field):
                by_customer = frappe.get_all(
                    doctype,
                    filters={customer_field: ["like", f"%{query}%"]},
                    fields=["name", customer_field],
                    limit=limit
                )
                for r in by_customer:
                    # Avoid duplicates
                    if not any(existing["name"] == r.name for existing in results):
                        results.append({
                            "name": r.name,
                            "customer_name": r.get(customer_field),
                            "link": f"https://{site_name}/app/{doctype_slug}/{r.name}",
                            "match_type": "customer"
                        })
    
    return results[:limit]


def get_document_title(doctype: str, docname: str) -> str:
    """
    Get a human-readable title for a document.
    
    For Sales Orders, this returns "SO-XXXXX - Customer Name"
    For Quotations, this returns "QTN-XXXXX - Customer Name"
    Etc.
    
    Args:
        doctype: The doctype
        docname: The document name
        
    Returns:
        A human-readable title
    """
    try:
        doc = frappe.get_doc(doctype, docname)
        
        # For transaction documents, try to get customer/party name
        if doctype in ["Sales Order", "Quotation", "Sales Invoice", "Delivery Note"]:
            customer_field = "customer_name" if frappe.get_meta(doctype).has_field("customer_name") else "customer"
            customer = getattr(doc, customer_field, None)
            if customer:
                return f"{docname} - {customer}"
                
        elif doctype == "Customer":
            customer_name = getattr(doc, "customer_name", None)
            if customer_name:
                return f"{docname} - {customer_name}"
                
        elif doctype == "Work Order":
            item = getattr(doc, "item_code", None)
            if item:
                return f"{docname} - {item}"
        
        # Fallback to just the name
        return docname
        
    except Exception:
        return docname
