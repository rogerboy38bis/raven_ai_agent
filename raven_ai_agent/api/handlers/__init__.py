"""
Raven AI Agent - Handler Modules
Mixin classes composing RaymondLucyAgent.execute_workflow_command
"""
from .manufacturing import ManufacturingMixin
from .bom import BOMMixin
from .web_search import WebSearchMixin
from .sales import SalesMixin
from .quotation import QuotationMixin
from .quality_management import QualityManagementMixin

__all__ = [
    "ManufacturingMixin",
    "BOMMixin",
    "WebSearchMixin",
    "SalesMixin",
    "QuotationMixin",
    "QualityManagementMixin",
]
