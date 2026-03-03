"""
Raven AI Agents (UPDATED)

Registers all agents for the 8-step fulfillment workflow:
  - BOMCreatorAgent (existing)
  - SalesOrderFollowupAgent (UPDATED — Steps 3, 6, 7)
  - ManufacturingAgent (NEW — Steps 1, 2, 4, 5)
  - PaymentAgent (NEW — Step 8)
  - WorkflowOrchestrator (NEW — Full pipeline controller)
  - RndAgent (existing)
  - IoTAgent (existing)
"""
from .bom_creator_agent import BOMCreatorAgent
from .sales_order_followup_agent import SalesOrderFollowupAgent
from .manufacturing_agent import ManufacturingAgent
from .payment_agent import PaymentAgent
from .workflow_orchestrator import WorkflowOrchestrator
from .rnd_agent import RndAgent
from .iot_agent import IoTAgent

__all__ = [
    "BOMCreatorAgent",
    "SalesOrderFollowupAgent",
    "ManufacturingAgent",
    "PaymentAgent",
    "WorkflowOrchestrator",
    "RndAgent",
    "IoTAgent",
]
