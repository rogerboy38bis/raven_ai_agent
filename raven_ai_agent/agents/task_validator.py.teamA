# task_validator.py - Bridge to DataQualityScannerSkill
# This file redirects pipeline commands to the actual scanner implementation

from __future__ import unicode_literals
import frappe
from frappe import _
import re
from raven_ai_agent.skills.data_quality_scanner.skill import DataQualityScannerSkill

class TaskValidator:
    """Task Validator Agent - Bridges to DataQualityScannerSkill"""
    
    def __init__(self):
        self.scanner = DataQualityScannerSkill()
    
    def handle(self, query: str, context: dict = None) -> dict:
        """Handle task validation requests"""
        if not frappe.db:
            return {
                "success": False,
                "error": "Frappe database not available"
            }
        
        query_lower = query.lower()
        
        # Check for SAL-QTN pattern (quotations)
        qtn_match = re.search(r'(SAL-QTN-\d+-\d+)', query, re.IGNORECASE)
        if qtn_match and ('pipeline' in query_lower or 'diagnose' in query_lower):
            doc_name = qtn_match.group(1).upper()
            # Llamar al scanner con un comando diagnose
            result = self.scanner.handle(f"diagnose {doc_name}")
            
            # Si el scanner devuelve un resultado, lo formateamos
            if isinstance(result, dict):
                if result.get("success"):
                    # Intentar obtener el diagnóstico formateado
                    try:
                        from frappe import _
                        # Usar el método privado de formato si existe
                        if hasattr(self.scanner, '_format_quotation_diagnosis'):
                            formatted = self.scanner._format_quotation_diagnosis(result)
                            return {
                                "success": True,
                                "response": formatted,
                                "raw_data": result
                            }
                    except:
                        pass
                    return result
            return {"success": True, "response": str(result)}
        
        # Check for QUOT pattern (alternative prefix)
        quot_match = re.search(r'(QUOT-\d+-\d+)', query, re.IGNORECASE)
        if quot_match and ('pipeline' in query_lower or 'diagnose' in query_lower):
            doc_name = quot_match.group(1).upper()
            result = self.scanner.handle(f"diagnose {doc_name}")
            if isinstance(result, dict):
                return result
            return {"success": True, "response": str(result)}
        
        # Check for SO pattern (sales orders)
        so_match = re.search(r'(SO-[\w-]+)', query, re.IGNORECASE)
        if so_match:
            doc_name = so_match.group(1).upper()
            result = self.scanner.handle(f"diagnose {doc_name}")
            if isinstance(result, dict):
                return result
            return {"success": True, "response": str(result)}
        
        # Para otros comandos, pasar al scanner directamente
        result = self.scanner.handle(query)
        if isinstance(result, dict):
            return result
        return {"success": True, "response": str(result)}

# For backward compatibility
def handle_task_validator(query, context=None):
    validator = TaskValidator()
    return validator.handle(query, context)
