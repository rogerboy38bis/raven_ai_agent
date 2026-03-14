# task_validator.py - UNIFIED VERSION (Team A + Team B)
# Combina:
# - Team A: Bridge to DataQualityScannerSkill (pipeline SAL-QTN, diagnose)
# - Team B: BUG15 fix, SO resolution, audit pipeline

from __future__ import unicode_literals
import frappe
from frappe import _
import re
from raven_ai_agent.skills.data_quality_scanner.skill import DataQualityScannerSkill

class TaskValidator:
    """Task Validator Agent - Unified version (Team A + Team B)"""
    
    def __init__(self):
        self.scanner = DataQualityScannerSkill()
    
    # ===== TEAM B's FUNCTIONS =====
    def _resolve_so_name(self, query):
        """BUG15 fix - Resolve SO name from prefix
        Customer names can contain (), commas, dots — regex can't match them.
        Returns a match-like object with group() returning the full SO name, or None.
        """
        m = re.search(r'(SAL-ORD-\d+-\d+|SO-\d{3,5})', query, re.IGNORECASE)
        if not m:
            return None
        prefix = m.group(1).upper()
        full_name = frappe.db.get_value("Sales Order",
            {"name": ["like", f"{prefix}%"], "docstatus": ["!=", 2]}, "name")
        if full_name:
            class SOMatch:
                def group(self, n):
                    return full_name
            return SOMatch()
        return None
    
    def _audit_pipeline(self, so_name):
        """Team B's pipeline audit functionality"""
        # Aquí puedes agregar la lógica completa del otro equipo
        # Por ahora, un placeholder
        return {
            "success": True, 
            "response": f"Audit pipeline for {so_name} - Team B functionality"
        }
    
    # ===== TEAM A's FUNCTIONS =====
    def _format_quotation_response(self, result):
        """Format quotation diagnosis response"""
        try:
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
    
    def _handle_quotation_pipeline(self, qtn_name):
        """Team A's quotation pipeline diagnosis"""
        result = self.scanner.handle(f"diagnose {qtn_name}")
        if isinstance(result, dict):
            if result.get("success"):
                return self._format_quotation_response(result)
            return result
        return {"success": True, "response": str(result)}
    
    # ===== UNIFIED HANDLER =====
    def handle(self, query: str, context: dict = None) -> dict:
        """Unified handler - processes both team's commands"""
        if not frappe.db:
            return {
                "success": False,
                "error": "Frappe database not available"
            }
        
        query_lower = query.lower()
        
        # TEAM B's commands (audit, validate, etc.)
        if 'audit' in query_lower and ('pipeline' in query_lower or 'so-' in query_lower):
            so_match = self._resolve_so_name(query)
            if so_match:
                return self._audit_pipeline(so_match.group(0))
        
        # TEAM A's commands (pipeline, diagnose for quotations)
        qtn_match = re.search(r'(SAL-QTN-\d+-\d+)', query, re.IGNORECASE)
        if qtn_match and ('pipeline' in query_lower or 'diagnose' in query_lower):
            return self._handle_quotation_pipeline(qtn_match.group(1).upper())
        
        quot_match = re.search(r'(QUOT-\d+-\d+)', query, re.IGNORECASE)
        if quot_match and ('pipeline' in query_lower or 'diagnose' in query_lower):
            return self._handle_quotation_pipeline(quot_match.group(1).upper())
        
        # TEAM B's SO validation
        so_match = self._resolve_so_name(query)
        if so_match and ('validate' in query_lower or 'check' in query_lower):
            # Handle SO validation
            doc_name = so_match.group(0)
            result = self.scanner.handle(f"diagnose {doc_name}")
            if isinstance(result, dict):
                return result
            return {"success": True, "response": str(result)}
        
        # Check for SO pattern (sales orders) - Team A original
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
