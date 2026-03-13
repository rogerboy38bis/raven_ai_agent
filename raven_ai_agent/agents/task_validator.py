# task_validator.py - Bridge to DataQualityScannerSkill
# This file redirects pipeline commands to the actual scanner implementation

from __future__ import unicode_literals
import frappe
from frappe import _
import re

class TaskValidator:
    """Task Validator Agent - Bridges to DataQualityScannerSkill"""
    
    def __init__(self):
        # La importación se hace dentro de métodos para evitar problemas de contexto
        self._scanner = None
    
    @property
    def scanner(self):
        """Lazy import of scanner to avoid context issues"""
        if self._scanner is None:
            from raven_ai_agent.skills.data_quality_scanner.skill import DataQualityScannerSkill
            self._scanner = DataQualityScannerSkill()
        return self._scanner
    
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
        if qtn_match:
            doc_name = qtn_match.group(1).upper()
            return self.scanner.diagnose_quotation_pipeline(doc_name)
        
        # Check for QUOT pattern
        quot_match = re.search(r'(QUOT-\d+-\d+)', query, re.IGNORECASE)
        if quot_match:
            doc_name = quot_match.group(1).upper()
            return self.scanner.diagnose_quotation_pipeline(doc_name)
        
        # Check for SO pattern (sales orders)
        so_match = re.search(r'(SO-[\w-]+)', query, re.IGNORECASE)
        if so_match:
            doc_name = so_match.group(1).upper()
            return self.scanner.diagnose_pipeline(doc_name)
        
        # Default response
        return {
            "success": False,
            "error": "No valid document ID found. Use format: SAL-QTN-YYYY-NNNNN or SO-XXXXX"
        }

# For backward compatibility
def handle_task_validator(query, context=None):
    validator = TaskValidator()
    return validator.handle(query, context)
