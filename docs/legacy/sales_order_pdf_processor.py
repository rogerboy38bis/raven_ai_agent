"""
Archived Server Script: Sales Order PDF Processor

V13.6.0 P3 Server Script Migration
Decision: DEL / archived
Script Type: DocType Event
Reference DocType: Sales Order
Disabled: 1

Runtime status:
  DO NOT IMPORT. Archive only.
"""

ORIGINAL_SCRIPT = """
# Ultra-simplified Sales Order Processor for Frappe Cloud

# Main processing function
def process_order(doc):
    try:
        # Create basic response structure
        result = {
            'status': 'success',
            'data': {
                'doctype': 'Sales Order',
                'items': [{
                    'item_code': 'default_item',
                    'qty': 1
                }]
            }
        }
        
        # Directly use doc as dictionary (no JSON parsing needed)
        if 'name' in doc:
            result['data']['name'] = doc['name']
        if 'customer' in doc:
            result['data']['customer'] = doc['customer']
        if 'po_no' in doc:
            result['data']['po_no'] = doc['po_no']
        
        # Simple text extraction from terms
        terms = doc.get('terms', '')
        if 'Codigo a Facturar' in terms:
            result['data']['custom_codigo'] = '0334'  # Hardcoded example
        
        return result
        
    except Exception as e:
        return {
            'status': 'error',
            'message': str(e)
        }

# Direct execution - doc is already available as a dict in server scripts
result = process_order(doc)
frappe.response.update(result)
"""
