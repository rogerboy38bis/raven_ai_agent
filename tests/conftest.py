"""
Pytest configuration for raven_ai_agent unit tests.

This conftest.py fixes the import path collision issue where pytest picks up
the outer __init__.py (apps/raven_ai_agent/__init__.py) instead of the inner
package (apps/raven_ai_agent/raven_ai_agent/).

Uses autouse fixture to clear sys.modules before each test.
"""
import sys
import importlib
from pathlib import Path
from unittest.mock import MagicMock
import pytest


PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)


@pytest.fixture(autouse=True)
def fix_imports():
    """Clear raven_ai_agent modules from sys.modules before each test"""
    for k in list(sys.modules):
        if k.startswith("raven_ai_agent"):
            del sys.modules[k]
    if PROJECT_ROOT in sys.path:
        sys.path.remove(PROJECT_ROOT)
    sys.path.insert(0, PROJECT_ROOT)
    importlib.import_module("raven_ai_agent")
    yield


@pytest.fixture(autouse=True)
def fix_frappe_mocks():
    """Ensure frappe module always has proper Exception classes after patches"""
    yield
    
    # After each test, fix the frappe module in sys.modules
    if "frappe" in sys.modules:
        frappe = sys.modules["frappe"]
        # Only fix if it's a MagicMock (patched version)
        if isinstance(frappe, MagicMock):
            # Use type() with 3rd arg {} to create proper Exception subclasses
            frappe.DoesNotExistError = type('DoesNotExistError', (Exception,), {})
            frappe.ValidationError = type('ValidationError', (Exception,), {})
            frappe.PermissionError = type('PermissionError', (Exception,), {})
            frappe._ = lambda x: x


def pytest_configure(config):
    """Setup mock frappe module with proper Exception classes"""
    # Use type() with 3rd arg {} to create proper Exception subclasses
    DoesNotExistError = type('DoesNotExistError', (Exception,), {})
    ValidationError = type('ValidationError', (Exception,), {})
    PermissionError = type('PermissionError', (Exception,), {})
    
    mock_frappe = MagicMock()
    mock_frappe.local = MagicMock()
    mock_frappe.db = MagicMock()
    mock_frappe.utils = MagicMock()
    mock_frappe._ = lambda x: x
    mock_frappe.throw = MagicMock(side_effect=Exception)
    
    # Set proper Exception classes
    mock_frappe.DoesNotExistError = DoesNotExistError
    mock_frappe.ValidationError = ValidationError
    mock_frappe.PermissionError = PermissionError
    
    sys.modules["frappe"] = mock_frappe
    sys.modules["frappe.utils"] = mock_frappe.utils
    sys.modules["frappe.model"] = MagicMock()
    sys.modules["frappe.model.document"] = MagicMock()
    sys.modules["frappe.utils.data"] = MagicMock()
    sys.modules["erpnext"] = MagicMock()
    sys.modules["erpnext.stock"] = MagicMock()
    sys.modules["erpnext.stock.doctype"] = MagicMock()
    sys.modules["erpnext.stock.doctype.stock_entry"] = MagicMock()
    sys.modules["erpnext.selling"] = MagicMock()
    sys.modules["erpnext.selling.doctype"] = MagicMock()
    sys.modules["erpnext.selling.doctype.sales_order"] = MagicMock()
    sys.modules["erpnext.controllers"] = MagicMock()
    sys.modules["erpnext.controllers.stock_controller"] = MagicMock()
    sys.modules["erpnext.manufacturing"] = MagicMock()
    sys.modules["erpnext.manufacturing.doctype"] = MagicMock()
    sys.modules["erpnext.manufacturing.doctype.work_order"] = MagicMock()
    sys.modules["erpnext.manufacturing.doctype.work_order.work_order"] = MagicMock()
    sys.modules["erpnext.accounts"] = MagicMock()
    sys.modules["erpnext.accounts.doctype"] = MagicMock()
    sys.modules["erpnext.accounts.doctype.payment_entry"] = MagicMock()
    sys.modules["erpnext.accounts.doctype.payment_entry.payment_entry"] = MagicMock()
