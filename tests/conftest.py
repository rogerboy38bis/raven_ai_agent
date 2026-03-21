"""
Pytest configuration for raven_ai_agent unit tests.

This conftest.py fixes the import path collision issue where pytest picks up
the outer __init__.py (apps/raven_ai_agent/__init__.py) instead of the inner
package (apps/raven_ai_agent/raven_ai_agent/).

Uses autouse fixture to clear sys.modules before each test.
"""
import sys
import types
from unittest.mock import MagicMock
import pytest


PROJECT_ROOT = "/workspace/raven_ai_agent"


# === REAL exception classes matching frappe/exceptions.py hierarchy ===
class ValidationError(Exception):
    http_status_code = 417


class DoesNotExistError(ValidationError):
    http_status_code = 404
    def __init__(self, *args, doctype=None):
        super().__init__(*args)
        self.doctype = doctype


class PermissionError(Exception):
    http_status_code = 403


class NameError(Exception):
    http_status_code = 409


class DuplicateEntryError(NameError):
    pass


class MandatoryError(ValidationError):
    pass


class LinkValidationError(ValidationError):
    pass


class DataError(ValidationError):
    pass


class AuthenticationError(Exception):
    http_status_code = 401


class DocumentLockedError(ValidationError):
    pass


class TimestampMismatchError(ValidationError):
    pass


class LinkExistsError(ValidationError):
    pass


# Store in dict for easy re-application
FRAPPE_EXCEPTIONS = {
    'ValidationError': ValidationError,
    'DoesNotExistError': DoesNotExistError,
    'PermissionError': PermissionError,
    'NameError': NameError,
    'DuplicateEntryError': DuplicateEntryError,
    'MandatoryError': MandatoryError,
    'LinkValidationError': LinkValidationError,
    'DataError': DataError,
    'AuthenticationError': AuthenticationError,
    'DocumentLockedError': DocumentLockedError,
    'TimestampMismatchError': TimestampMismatchError,
    'LinkExistsError': LinkExistsError,
}


def _create_mock_frappe_module():
    """Create a mock frappe module with REAL exception classes"""
    # Create a real module type, not MagicMock
    frappe_module = types.ModuleType("frappe")
    
    # Apply real exception classes
    for name, exc_class in FRAPPE_EXCEPTIONS.items():
        setattr(frappe_module, name, exc_class)
    
    # Also set on frappe.exceptions
    frappe_module.exceptions = types.ModuleType("frappe.exceptions")
    for name, exc_class in FRAPPE_EXCEPTIONS.items():
        setattr(frappe_module.exceptions, name, exc_class)
    
    # Mock common frappe functions/attributes
    frappe_module._dict = lambda x=None: dict(x) if x else {}
    frappe_module.as_json = lambda x: str(x)
    frappe_module._ = lambda x: x
    
    frappe_module.local = MagicMock()
    frappe_module.db = MagicMock()
    frappe_module.db.get_value = MagicMock(return_value=0)
    frappe_module.db.get_all = MagicMock(return_value=[])
    frappe_module.utils = MagicMock()
    frappe_module.throw = MagicMock(side_effect=Exception)
    frappe_module.get_doc = MagicMock()
    frappe_module.new_doc = MagicMock()
    frappe_module.copy_doc = MagicMock()
    frappe_module.get_all = MagicMock(return_value=[])
    frappe_module.get_value = MagicMock()
    frappe_module.exists = MagicMock()
    
    # frappe.whitelist decorator - used to expose functions to web API
    # Must work both as @frappe.whitelist() and @frappe.whitelist
    class _WhitelistDecorator:
        """Mock whitelist decorator that works with or without parentheses"""
        def __call__(self, fn=None, **kwargs):
            if fn is None:
                # Called with parentheses @frappe.whitelist()
                return lambda f: f
            # Called without parentheses @frappe.whitelist
            return fn
    
    frappe_module.whitelist = _WhitelistDecorator()
    
    # Mock frappe.utils
    frappe_module.utils = types.ModuleType("frappe.utils")
    frappe_module.utils.nowdate = lambda: "2026-03-21"
    frappe_module.utils.today = lambda: "2026-03-21"
    frappe_module.utils.getdate = lambda x=None: x
    frappe_module.utils.now_datetime = lambda: "2026-03-21 12:00:00"
    frappe_module.utils.add_days = lambda date, days: date
    frappe_module.utils.date_diff = lambda end, start: 0
    frappe_module.utils.fmt_money = lambda x: str(x)
    frappe_module.utils.flt = lambda x: float(x) if x else 0.0
    frappe_module.utils.cint = lambda x: int(x) if x else 0
    frappe_module.utils.cstr = lambda x: str(x) if x else ""
    
    # Mock frappe.defaults
    frappe_module.defaults = MagicMock()
    frappe_module.defaults.get_user_default = MagicMock(return_value="AMB-Wellness")
    
    # Mock frappe.log_error
    frappe_module.log_error = MagicMock()
    
    # Mock frappe.db.commit and rollback
    frappe_module.db.commit = MagicMock()
    frappe_module.db.rollback = MagicMock()
    
    return frappe_module


@pytest.fixture(autouse=True)
def fix_imports():
    """Clear raven_ai_agent modules from sys.modules before each test"""
    import importlib
    
    for k in list(sys.modules):
        if k.startswith("raven_ai_agent"):
            del sys.modules[k]
    if PROJECT_ROOT in sys.path:
        sys.path.remove(PROJECT_ROOT)
    sys.path.insert(0, PROJECT_ROOT)
    importlib.import_module("raven_ai_agent")
    yield


@pytest.fixture(autouse=True)
def restore_frappe_exceptions():
    """Restore real exception classes after each test.
    
    @patch decorators may replace frappe attributes with MagicMock.
    This fixture runs AFTER each test to fix them back.
    """
    yield  # test runs here
    
    # Restore after test - fix ALL frappe-related modules
    frappe_mod = sys.modules.get("frappe")
    if frappe_mod:
        for name, exc_class in FRAPPE_EXCEPTIONS.items():
            setattr(frappe_mod, name, exc_class)
        
        # Also fix frappe.exceptions
        if hasattr(frappe_mod, 'exceptions') and isinstance(frappe_mod.exceptions, MagicMock):
            frappe_mod.exceptions = types.ModuleType("frappe.exceptions")
            for name, exc_class in FRAPPE_EXCEPTIONS.items():
                setattr(frappe_mod.exceptions, name, exc_class)
    
    # Fix any other frappe sub-modules
    for module_name in list(sys.modules.keys()):
        if module_name.startswith("frappe."):
            mod = sys.modules[module_name]
            if hasattr(mod, 'frappe'):
                frappe_attr = getattr(mod, 'frappe')
                if isinstance(frappe_attr, MagicMock):
                    for name, exc_class in FRAPPE_EXCEPTIONS.items():
                        setattr(frappe_attr, name, exc_class)


def pytest_configure(config):
    """Setup mock frappe module with proper Exception classes"""
    # Create and inject mock frappe module BEFORE any test imports
    mock_frappe = _create_mock_frappe_module()
    sys.modules["frappe"] = mock_frappe
    
    # Mock frappe sub-modules
    # Ensure frappe.db has proper return values
    mock_frappe.db.get_value.return_value = 0
    mock_frappe.db.get_all.return_value = []
    
    frappe_utils = types.ModuleType("frappe.utils")
    frappe_utils.nowdate = lambda: "2026-03-21"
    frappe_utils.today = lambda: "2026-03-21"
    frappe_utils.getdate = lambda x=None: x
    frappe_utils.now_datetime = lambda: "2026-03-21 12:00:00"
    frappe_utils.add_days = lambda date, days: date
    frappe_utils.date_diff = lambda end, start: 0
    frappe_utils.fmt_money = lambda x: str(x)
    frappe_utils.flt = lambda x: float(x) if x else 0.0
    frappe_utils.cint = lambda x: int(x) if x else 0
    frappe_utils.cstr = lambda x: str(x) if x else ""
    sys.modules["frappe.utils"] = frappe_utils
    
    frappe_defaults = types.ModuleType("frappe.defaults")
    frappe_defaults.get_user_default = MagicMock(return_value="AMB-Wellness")
    sys.modules["frappe.defaults"] = frappe_defaults
    
    sys.modules["frappe.model"] = MagicMock()
    sys.modules["frappe.model.document"] = MagicMock()
    sys.modules["frappe.utils.data"] = MagicMock()
    sys.modules["frappe.exceptions"] = mock_frappe.exceptions
    
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
