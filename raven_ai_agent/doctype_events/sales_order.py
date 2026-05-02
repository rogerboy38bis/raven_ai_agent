"""
V13.6.0 P3 Migration: pdf_to_erpnext_processor
Original Server Script: pdf_to_erpnext_processor
Type: DocType Event (Sales Order)
"""

import frappe
from frappe import _
from frappe.utils import nowdate, getdate, flt, cstr

# frappe/server_scripts/sales_order_pdf_processor.py

#import frappe
#from frappe import _
#from frappe.utils import nowdate, getdate, flt, cstr
#from frappe.model.document import Document

#@frappe.whitelist()
def process_sales_order_pdf(pdf_content, sales_order_name=None):
    """
    Process PDF content and update Sales Order with extracted data
    Whitelisted for API calls
    """
    try:
        # Validate input
        if not pdf_content:
            frappe.throw(_("PDF content is required"))
        
        # Get or create Sales Order
        if sales_order_name and frappe.db.exists("Sales Order", sales_order_name):
            so = frappe.get_doc("Sales Order", sales_order_name)
        else:
            so = frappe.new_doc("Sales Order")
            so.company = frappe.defaults.get_user_default("company")
            so.transaction_date = nowdate()
        
        # Extract data from PDF content
        extracted_data = extract_order_data_from_pdf(pdf_content)
        
        # Update Sales Order with extracted data
        update_sales_order(so, extracted_data)
        
        # Save the document
        so.save()
        
        return {
            "status": "success",
            "sales_order": so.name,
            "message": _("Sales Order processed successfully")
        }
        
    except Exception as e:
        frappe.log_error(
            title=_("PDF Processing Error"),
            message=f"Error processing PDF for Sales Order: {str(e)}"
        )
        return {
            "status": "error",
            "message": _("Error processing PDF: {0}").format(str(e))
        }

def extract_order_data_from_pdf(pdf_content):
    """
    Extract structured data from PDF text content using safe methods
    """
    data = {
        "doctype": "Sales Order",
        "items": [],
        "custom_fields": {}
    }
    
    # Handle JSON input
    text_content = pdf_content
    if pdf_content.strip().startswith('{'):
        try:
            content_data = frappe.parse_json(pdf_content)
            text_content = content_data.get("text_in_pdf", pdf_content)
        except:
            pass
    
    # Extract basic information using string methods
    data.update(extract_basic_info(text_content))
    data.update(extract_customer_info(text_content))
    data.update(extract_product_info(text_content))
    data.update(extract_specifications(text_content))
    
    return data

def extract_basic_info(text):
    """Extract basic order information using string methods"""
    info = {}
    
    # Order number
    if "Numero Pedido" in text:
        parts = text.split("Numero Pedido")
        if len(parts) > 1:
            order_part = parts[1].split()[0] if parts[1].split() else ""
            info["name"] = order_part.strip()
    
    # Purchase order
    if "Orde de Compra" in text:
        parts = text.split("Orde de Compra")
        if len(parts) > 1:
            po_part = parts[1].split()[0] if parts[1].split() else ""
            info["po_no"] = po_part.strip()
    
    # Dates - simplified date extraction
    date_patterns = [
        ("Fecha de Registro", "registration_date"),
        ("Fecha de Orden", "po_date"),
        ("Fecha de Entrega", "delivery_date")
    ]
    
    for pattern, field in date_patterns:
        if pattern in text:
            parts = text.split(pattern)
            if len(parts) > 1:
                date_part = parts[1].split()[0] if parts[1].split() else ""
                if "/" in date_part:
                    info[field] = parse_date_string(date_part)
    
    return info

def extract_customer_info(text):
    """Extract customer information"""
    info = {}
    
    # Customer name
    if "Cliente\\Distribuidor" in text:
        parts = text.split("Cliente\\Distribuidor")
        if len(parts) > 1:
            customer_part = parts[1].split("\n")[0] if "\n" in parts[1] else parts[1]
            customer_name = customer_part.strip()
            info["customer"] = customer_name
            info["customer_name"] = customer_name
    
    # Subcliente
    if "Subcliente" in text:
        parts = text.split("Subcliente")
        if len(parts) > 1:
            subclient_part = parts[1].split("Codigo")[0] if "Codigo" in parts[1] else parts[1]
            info["custom_subcliente"] = subclient_part.strip()
    
    return info

def extract_product_info(text):
    """Extract product information"""
    info = {"items": []}
    
    # Look for product patterns
    lines = text.split("\n")
    for i, line in enumerate(lines):
        line = line.strip()
        
        # Simple pattern matching for product lines
        if len(line.split()) >= 3 and any(char.isdigit() for char in line.split()[0]):
            parts = line.split()
            try:
                # Try to parse as item code, quantity, unit
                item_code = parts[0]
                qty = flt(parts[1])
                uom = parts[2].replace('.', '')
                
                # Description is the rest of the line
                description = " ".join(parts[3:]) if len(parts) > 3 else item_code
                
                item = {
                    "item_code": find_matching_item(item_code, description),
                    "qty": qty,
                    "uom": uom,
                    "item_name": description,
                    "description": description
                }
                info["items"].append(item)
                
            except (ValueError, IndexError):
                continue
    
    return info

def extract_specifications(text):
    """Extract specifications and custom fields"""
    info = {"custom_fields": {}}
    
    # Observations
    if "Observaciones" in text:
        parts = text.split("Observaciones")
        if len(parts) > 1:
            obs_part = parts[1].split("TDS")[0] if "TDS" in parts[1] else parts[1]
            info["custom_fields"]["custom_observaciones"] = obs_part.strip()[:140]  # Limit length
    
    # Shipping methods
    shipping_methods = {
        "Terrestre": "custom_embarque_terrestre",
        "Maritimo": "custom_embarque_maritimo", 
        "Aereo": "custom_embarque_aereo"
    }
    
    for method, field in shipping_methods.items():
        if method.lower() in text.lower():
            info["custom_fields"][field] = f"✓ {method}"
    
    return info

def find_matching_item(item_code, description):
    """
    Find matching item in ERPNext system
    """
    # First try exact item code match
    if frappe.db.exists("Item", item_code):
        return item_code
    
    # Try partial match in item code
    items = frappe.get_all("Item", 
        filters={"item_code": ["like", f"%{item_code}%"]},
        fields=["item_code", "item_name"]
    )
    
    if items:
        return items[0].item_code
    
    # Try description match
    items = frappe.get_all("Item",
        filters={"item_name": ["like", f"%{description[:20]}%"]},
        fields=["item_code", "item_name"]
    )
    
    if items:
        return items[0].item_code
    
    # Return original code if no match found
    return item_code

def parse_date_string(date_str):
    """
    Parse date string safely
    """
    try:
        # Handle DD/MM/YY format
        if "/" in date_str:
            parts = date_str.split("/")
            if len(parts) == 3:
                day, month, year = parts
                year = f"20{year}" if len(year) == 2 else year
                return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    except:
        pass
    
    return nowdate()

def update_sales_order(sales_order, extracted_data):
    """
    Update Sales Order with extracted data
    """
    # Update basic fields
    for field in ["name", "po_no", "delivery_date"]:
        if field in extracted_data and extracted_data[field]:
            sales_order.set(field, extracted_data[field])
    
    # Update customer if not already set
    if "customer" in extracted_data and extracted_data["customer"] and not sales_order.customer:
        sales_order.customer = extracted_data["customer"]
        sales_order.customer_name = extracted_data.get("customer_name", extracted_data["customer"])
    
    # Add items if not already present
    if extracted_data.get("items") and not sales_order.items:
        for item_data in extracted_data["items"]:
            sales_order.append("items", {
                "item_code": item_data.get("item_code"),
                "qty": item_data.get("qty", 1),
                "uom": item_data.get("uom", "Nos"),
                "item_name": item_data.get("item_name"),
                "description": item_data.get("description")
            })
    
    # Update custom fields
    custom_fields = extracted_data.get("custom_fields", {})
    for field, value in custom_fields.items():
        if hasattr(sales_order, field):
            sales_order.set(field, value)

#@frappe.whitelist()
def get_pdf_processing_settings():
    """
    Get settings for PDF processing
    """
    return {
        "supported_fields": [
            "customer", "po_no", "delivery_date", "items",
            "custom_subcliente", "custom_observaciones",
            "custom_embarque_terrestre", "custom_embarque_maritimo", "custom_embarque_aereo"
        ],
        "required_fields": ["customer", "items"]
    }

# Client-side JavaScript integration
"""
// Example client-side usage:
frappe.call({
    method: 'your_app.sales_order_pdf_processor.process_sales_order_pdf',
    args: {
        pdf_content: pdfTextContent,
        sales_order_name: 'SO-01825-Barentz Italia Specchiasol' // optional
    },
    callback: function(response) {
        if (response.message.status === 'success') {
            frappe.show_alert('PDF processed successfully');
            frappe.set_route('Form', 'Sales Order', response.message.sales_order);
        } else {
            frappe.msgprint('Error: ' + response.message.message);
        }
    }
});
"""
