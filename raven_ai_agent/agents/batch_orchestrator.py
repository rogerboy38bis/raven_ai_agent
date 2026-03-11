"""
Batch Orchestrator — Generic Batch Processing for Raven AI Agent

A smart batch processor that can execute existing pipelines/commands on multiple documents.
This is the architecture the user requested: a "batcher that calls the whole pipeline or batch that has already been tested".

Supported batch operations:
  - batch run pipeline for [criteria] — Run full 8-step workflow for matching SOs
  - batch create invoices for [criteria] — Create SIs for matching SOs  
  - batch create delivery for [criteria] — Create DNs for matching SOs
  - batch submit for [criteria] — Submit matching SOs
  - batch status for [criteria] — Get pipeline status for matching SOs

Criteria can be:
  - "to bill" — SOs with status "To Bill" (has DN, needs SI)
  - "to deliver" — SOs with status "To Deliver" (needs DN)
  - "overdue" — SOs with past delivery_date not closed
  - "all" — All submitted SOs (filter by status)
  - [SO-NAME], [SO-NAME], ... — Specific list

Author: raven_ai_agent
"""
import frappe
import re
from typing import Dict, List, Optional
from frappe.utils import nowdate, getdate, flt, add_days
from datetime import datetime, timedelta


class BatchOrchestrator:
    """Generic batch processor that delegates to existing orchestrators"""
    
    def __init__(self, user: str = None):
        self.user = user or frappe.session.user
        self.site_name = frappe.local.site
        self.results = []
        self.errors = []
    
    def make_link(self, doctype: str, name: str) -> str:
        """Generate clickable markdown link"""
        slug = doctype.lower().replace(" ", "-")
        return f"[{name}](https://{self.site_name}/app/{slug}/{name})"
    
    # ========== CRITERIA PARSING ==========
    
    def parse_criteria(self, criteria: str) -> Dict:
        """Parse batch criteria and return filter dict"""
        criteria_lower = criteria.lower().strip()
        
        # Explicit SO names
        so_pattern = r'(SO-[\w-]+)'
        so_matches = re.findall(so_pattern, criteria, re.IGNORECASE)
        if so_matches:
            return {
                "type": "explicit",
                "so_names": [s.upper() for s in so_matches]
            }
        
        # Status-based criteria
        if "to bill" in criteria_lower:
            return {"type": "status", "status": "To Bill"}
        
        if "to deliver" in criteria_lower:
            return {"type": "status", "status": "To Deliver"}
        
        if "to deliver and bill" in criteria_lower:
            return {"type": "status", "status": "To Deliver and Bill"}
        
        if "overdue" in criteria_lower:
            return {"type": "overdue"}
        
        if "completed" in criteria_lower:
            return {"type": "status", "status": "Completed"}
        
        if "draft" in criteria_lower:
            return {"type": "status", "status": "Draft"}
        
        # Default: return empty
        return {"type": "unknown"}
    
    def find_sales_orders(self, criteria: Dict, limit: int = 20) -> List[Dict]:
        """Find Sales Orders matching criteria"""
        
        if criteria["type"] == "explicit":
            # Validate and return explicit SOs
            result = []
            for so_name in criteria["so_names"]:
                try:
                    so = frappe.get_doc("Sales Order", so_name)
                    result.append({
                        "name": so.name,
                        "customer": so.customer_name,
                        "grand_total": so.grand_total,
                        "currency": so.currency,
                        "status": so.status,
                        "delivery_date": so.delivery_date,
                        "docstatus": so.docstatus
                    })
                except frappe.DoesNotExistError:
                    self.errors.append({"so": so_name, "error": "Not found"})
            return result
        
        if criteria["type"] == "status":
            return frappe.get_all("Sales Order",
                filters={
                    "status": criteria["status"],
                    "docstatus": 1
                },
                fields=["name", "customer_name", "grand_total", "currency", "status", "delivery_date", "docstatus"],
                order_by="grand_total desc",
                limit=limit
            )
        
        if criteria["type"] == "overdue":
            today = nowdate()
            return frappe.get_all("Sales Order",
                filters={
                    "delivery_date": ["<", today],
                    "status": ["not in", ["Completed", "Closed", "Cancelled"]],
                    "docstatus": 1
                },
                fields=["name", "customer_name", "grand_total", "currency", "status", "delivery_date", "docstatus"],
                order_by="delivery_date asc",
                limit=limit
            )
        
        return []
    
    # ========== BATCH OPERATIONS ==========
    
    def batch_create_invoices(self, criteria: Dict, limit: int = 20) -> Dict:
        """Batch create Sales Invoices for matching SOs
        
        Strategy:
        1. Find SOs that have Delivery Notes but no Sales Invoice
        2. Use existing invoice creation logic
        3. Report results
        """
        from raven_ai_agent.api.sales import SalesMixin
        
        sales_mixin = SalesMixin()
        
        # Find SOs with DN but no SI
        ordenes = frappe.db.sql("""
            SELECT 
                so.name,
                so.customer_name,
                so.grand_total,
                so.currency,
                so.status
            FROM `tabSales Order` so
            INNER JOIN `tabDelivery Note Item` dni ON dni.against_sales_order = so.name AND dni.docstatus = 1
            INNER JOIN `tabDelivery Note` dn ON dn.name = dni.parent AND dn.docstatus = 1
            LEFT JOIN `tabSales Invoice Item` sii ON sii.sales_order = so.name AND sii.docstatus = 1
            LEFT JOIN `tabSales Invoice` si ON si.name = sii.parent AND si.docstatus = 1
            WHERE so.docstatus = 1
              AND so.status IN ('To Bill', 'To Deliver and Bill')
              AND si.name IS NULL
            GROUP BY so.name
            ORDER BY so.grand_total DESC
            LIMIT %s
        """, (limit,), as_dict=True)
        
        if not ordenes:
            return {
                "success": True,
                "message": "✅ No se encontraron órdenes con Nota de Entrega pendientes de facturar.",
                "processed": 0,
                "errors": 0
            }
        
        resultados = []
        errores = []
        
        for orden in ordenes:
            so_name = orden.name
            try:
                # Use the existing invoice creation logic from SalesMixin
                # We call create_sales_invoice directly
                from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
                agent = SalesOrderFollowupAgent(self.user)
                result = agent.create_sales_invoice(so_name, from_dn=True)
                
                if result.get("success"):
                    resultados.append({
                        "so": so_name,
                        "si": result.get("si_name", "created"),
                        "link": result.get("link", "")
                    })
                else:
                    errores.append({
                        "so": so_name,
                        "error": result.get("error", "Unknown error")
                    })
                    
            except Exception as e:
                errores.append({
                    "so": so_name,
                    "error": str(e)[:80]
                })
        
        # Build response
        msg = f"📋 **BATCH: Crear Facturas**\n\n"
        msg += f"**Encontradas:** {len(ordenes)}\n"
        msg += f"✅ **Procesadas:** {len(resultados)}\n"
        msg += f"❌ **Errores:** {len(errores)}\n\n"
        
        if resultados[:5]:
            msg += "**Facturas creadas:**\n"
            for r in resultados[:5]:
                msg += f"  • [{r['si']}](https://{self.site_name}/app/sales-invoice/{r['si']}) de {r['so']}\n"
        
        if errores[:5]:
            msg += "\n**Errores:**\n"
            for e in errores[:5]:
                msg += f"  • {e['so']}: {e['error']}\n"
        
        return {
            "success": len(errores) == 0,
            "message": msg,
            "processed": len(resultados),
            "errors": len(errores),
            "details": {
                "success": resultados,
                "errors": errores
            }
        }
    
    def batch_create_delivery_notes(self, criteria: Dict, limit: int = 20) -> Dict:
        """Batch create Delivery Notes for matching SOs"""
        
        # Find SOs that need DN (To Deliver or To Deliver and Bill)
        ordenes = frappe.get_all("Sales Order",
            filters={
                "status": ["in", ["To Deliver", "To Deliver and Bill"]],
                "docstatus": 1
            },
            fields=["name", "customer_name", "grand_total", "currency", "status", "delivery_date"],
            order_by="grand_total desc",
            limit=limit
        )
        
        if not ordenes:
            return {
                "success": True,
                "message": "✅ No se encontraron órdenes pendientes de entrega.",
                "processed": 0,
                "errors": 0
            }
        
        resultados = []
        errores = []
        
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        agent = SalesOrderFollowupAgent(self.user)
        
        for orden in ordenes:
            so_name = orden.name
            try:
                result = agent.create_delivery_note(so_name)
                
                if result.get("success"):
                    resultados.append({
                        "so": so_name,
                        "dn": result.get("dn_name", "created"),
                        "link": result.get("link", "")
                    })
                else:
                    errores.append({
                        "so": so_name,
                        "error": result.get("error", "Unknown error")
                    })
                    
            except Exception as e:
                errores.append({
                    "so": so_name,
                    "error": str(e)[:80]
                })
        
        msg = f"📋 **BATCH: Crear Notas de Entrega**\n\n"
        msg += f"**Encontradas:** {len(ordenes)}\n"
        msg += f"✅ **Procesadas:** {len(resultados)}\n"
        msg += f"❌ **Errores:** {len(errores)}\n\n"
        
        if resultados[:5]:
            msg += "**Notas de Entrega creadas:**\n"
            for r in resultados[:5]:
                msg += f"  • [{r['dn']}](https://{self.site_name}/app/delivery-note/{r['dn']}) de {r['so']}\n"
        
        if errores[:5]:
            msg += "\n**Errores:**\n"
            for e in errores[:5]:
                msg += f"  • {e['so']}: {e['error']}\n"
        
        return {
            "success": len(errores) == 0,
            "message": msg,
            "processed": len(resultados),
            "errors": len(errores),
            "details": {
                "success": resultados,
                "errors": errores
            }
        }
    
    def batch_run_pipeline(self, criteria: Dict, skip_steps: List[int] = None, limit: int = 10) -> Dict:
        """Batch run full pipeline for matching SOs
        
        This uses the WorkflowOrchestrator to run the complete 8-step workflow.
        """
        from raven_ai_agent.agents.workflow_orchestrator import WorkflowOrchestrator
        
        # Find SOs matching criteria
        sos = self.find_sales_orders(criteria, limit=limit)
        
        if not sos:
            return {
                "success": True,
                "message": "✅ No se encontraron órdenes que coincidan con el criterio.",
                "processed": 0,
                "errors": 0
            }
        
        resultados = []
        errores = []
        
        orchestrator = WorkflowOrchestrator(self.user)
        
        for so in sos:
            so_name = so["name"]
            try:
                result = orchestrator.run_full_cycle(
                    so_name=so_name,
                    skip_steps=skip_steps or []
                )
                
                if result.get("success"):
                    resultados.append({
                        "so": so_name,
                        "message": "Pipeline completado"
                    })
                else:
                    errores.append({
                        "so": so_name,
                        "error": result.get("error", "Pipeline failed")
                    })
                    
            except Exception as e:
                errores.append({
                    "so": so_name,
                    "error": str(e)[:80]
                })
        
        msg = f"📋 **BATCH: Ejecutar Pipeline**\n\n"
        msg += f"**Encontradas:** {len(sos)}\n"
        msg += f"✅ **Completadas:** {len(resultados)}\n"
        msg += f"❌ **Errores:** {len(errores)}\n\n"
        
        if resultados[:5]:
            msg += "**SOs procesadas:**\n"
            for r in resultados[:5]:
                msg += f"  • {r['so']}: ✅\n"
        
        if errores[:5]:
            msg += "\n**Errores:**\n"
            for e in errores[:5]:
                msg += f"  • {e['so']}: {e['error']}\n"
        
        return {
            "success": len(errores) == 0,
            "message": msg,
            "processed": len(resultados),
            "errors": len(errores),
            "details": {
                "success": resultados,
                "errors": errores
            }
        }
    
    def batch_status(self, criteria: Dict, limit: int = 20) -> Dict:
        """Get pipeline status for multiple SOs"""
        
        sos = self.find_sales_orders(criteria, limit=limit)
        
        if not sos:
            return {
                "success": True,
                "message": "✅ No se encontraron órdenes.",
                "count": 0
            }
        
        from raven_ai_agent.agents.workflow_orchestrator import WorkflowOrchestrator
        orchestrator = WorkflowOrchestrator(self.user)
        
        msg = f"📊 **Pipeline Status — {len(sos)} Órdenes**\n\n"
        
        for so in sos:
            result = orchestrator.get_pipeline_status(so["name"])
            if result.get("success"):
                progress = result.get("progress", 0)
                msg += f"**{so['name']}** — {progress}% completo\n"
        
        return {
            "success": True,
            "message": msg,
            "count": len(sos)
        }
    
    # ========== COMMAND PARSER ==========
    
    def process_command(self, message: str) -> str:
        """Process incoming batch command
        
        Commands:
          @batch create invoices for to bill
          @batch create delivery for to deliver
          @batch run pipeline for overdue
          @batch status for all
          @batch help
        """
        message_lower = message.lower().strip()
        
        # HELP
        if "help" in message_lower or "ayuda" in message_lower:
            return self._help_text()
        
        # Parse operation
        operation = None
        if "create invoice" in message_lower or "crear factura" in message_lower:
            operation = "invoice"
        elif "create delivery" in message_lower or "crear entrega" in message_lower:
            operation = "delivery"
        elif "run pipeline" in message_lower or "ejecutar pipeline" in message_lower:
            operation = "pipeline"
        elif "status" in message_lower:
            operation = "status"
        
        if not operation:
            return self._help_text()
        
        # Parse criteria
        # Extract everything after "for" or "para"
        criteria_match = re.search(r'(?:for|para)\s+(.+?)$', message, re.IGNORECASE)
        if not criteria_match:
            return "❌ Specify criteria. Example: `@batch create invoices for to bill`"
        
        criteria_text = criteria_match.group(1).strip()
        criteria = self.parse_criteria(criteria_text)
        
        if criteria["type"] == "unknown":
            return f"❌ Unknown criteria: '{criteria_text}'. Use: to bill, to deliver, overdue, or SO names."
        
        # Extract optional limits
        limit_match = re.search(r'limit\s+(\d+)', message_lower)
        limit = int(limit_match.group(1)) if limit_match else 10
        
        # Extract skip steps
        skip_match = re.search(r'skip\s+\[?([\d,\s]+)\]?', message, re.IGNORECASE)
        skip_steps = [int(s.strip()) for s in skip_match.group(1).split(",")] if skip_match else None
        
        # Execute batch operation
        if operation == "invoice":
            result = self.batch_create_invoices(criteria, limit=limit)
        elif operation == "delivery":
            result = self.batch_create_delivery_notes(criteria, limit=limit)
        elif operation == "pipeline":
            result = self.batch_run_pipeline(criteria, skip_steps=skip_steps, limit=limit)
        elif operation == "status":
            result = self.batch_status(criteria, limit=limit)
        else:
            return self._help_text()
        
        return result.get("message", "Unknown result")
    
    def _help_text(self) -> str:
        return (
            "📋 **Batch Orchestrator — Comandos**\n\n"
            "El procesador de lotes inteligente que delega a pipelines existentes.\n\n"
            "**Operaciones:**\n"
            "`@batch create invoices for [criterio]` — Crear facturas para órdenes coincidentes\n"
            "`@batch create delivery for [criterio]` — Crear notas de entrega\n"
            "`@batch run pipeline for [criterio]` — Ejecutar pipeline completo (8 pasos)\n"
            "`@batch status for [criterio]` — Ver estado del pipeline\n\n"
            "**Criterios:**\n"
            "`to bill` — Órdenes con status 'To Bill' (tienen DN, necesitan SI)\n"
            "`to deliver` — Órdenes con status 'To Deliver'\n"
            "`overdue` — Órdenes con fecha de entrega vencida\n"
            "`SO-12345, SO-12346` — Lista explícita de órdenes\n\n"
            "**Opciones:**\n"
            "`limit N` — Límite de órdenes a procesar (default: 10)\n"
            "`skip [1,2]` — Saltar pasos del pipeline\n\n"
            "**Ejemplos:**\n"
            "```\n"
            "@batch create invoices for to bill\n"
            "@batch create delivery for to deliver limit 5\n"
            "@batch run pipeline for overdue skip [1,2,3]\n"
            "@batch status for all\n"
            "```"
        )


def execute_batch_command(message: str, user: str = None) -> str:
    """Entry point for batch commands from agent.py"""
    batcher = BatchOrchestrator(user)
    return batcher.process_command(message)
