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


# Define REAL exception classes BEFORE any patching
# These must be proper exception subclasses, not MagicMock objects
class FrappeDoesNotExistError(Exception):
    """Exception raised when a Frappe document does not exist"""
    pass


class FrappeValidationError(Exception):
    """Exception raised for validation errors in Frappe"""
    pass


class FrappePermissionError(Exception):
    """Exception raised for permission errors in Frappe"""
    pass


class FrappeDuplicateEntryError(Exception):
    """Exception raised when a duplicate entry is created"""
    pass


def _setup_frappe_exceptions(mock_obj):
    """Helper to set up proper exception classes on a mock frappe object"""
    # Use the real exception classes we defined above
    mock_obj.DoesNotExistError = FrappeDoesNotExistError
    mock_obj.ValidationError = FrappeValidationError
    mock_obj.PermissionError = FrappePermissionError
    mock_obj.DuplicateEntryError = FrappeDuplicateEntryError
    mock_obj._ = lambda x: x
    mock_obj.throw = MagicMock(side_effect=Exception)
    return mock_obj


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
    
    # After each test, fix ALL frappe-related modules in sys.modules
    for module_name in list(sys.modules.keys()):
        if module_name == "frappe" or module_name.startswith("frappe."):
            mod = sys.modules[module_name]
            if isinstance(mod, MagicMock):
                _setup_frappe_exceptions(mod)
        
        # Also fix any erpnext modules that might have frappe references
        if module_name.startswith("erpnext"):
            mod = sys.modules[module_name]
            if isinstance(mod, MagicMock):
                # Check if mod has frappe as an attribute
                if hasattr(mod, 'frappe'):
                    frappe_attr = getattr(mod, 'frappe')
                    if isinstance(frappe_attr, MagicMock):
                        _setup_frappe_exceptions(frappe_attr)


def pytest_configure(config):
    """Setup mock frappe module with proper Exception classes"""
    # Create mock frappe module
    mock_frappe = MagicMock()
    mock_frappe.local = MagicMock()
    mock_frappe.db = MagicMock()
    mock_frappe.utils = MagicMock()
    
    # Set up proper exception classes using our real exception classes
    _setup_frappe_exceptions(mock_frappe)
    
    # Register all frappe-related modules
    sys.modules["frappe"] = mock_frappe
    sys.modules["frappe.utils"] = mock_frappe.utils
    sys.modules["frappe.model"] = MagicMock()
    sys.modules["frappe.model.document"] = MagicMock()
    sys.modules["frappe.utils.data"] = MagicMock()
    sys.modules["frappe.exceptions"] = MagicMock()
    sys.modules["frappe.exceptions.ValidationError"] = FrappeValidationError
    sys.modules["frappe.exceptions.DoesNotExistError"] = FrappeDoesNotExistError
    
    # Register erpnext modules
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
