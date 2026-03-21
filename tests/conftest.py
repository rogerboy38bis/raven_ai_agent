"""
Pytest configuration for raven_ai_agent unit tests.

This conftest.py provides a comprehensive mock of the frappe module
for unit testing without requiring a real Frappe/ERPNext installation.
"""
import sys
import types
from unittest.mock import MagicMock
import pytest


PROJECT_ROOT = "/workspace/raven_ai_agent"


# Exception classes must be defined BEFORE _FrappeMock
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


class _FrappeMock(MagicMock):
    """MagicMock subclass that always returns real exception classes.
    
    When @patch replaces frappe with a new MagicMock, the exception classes
    become MagicMock objects which can't be used in except/raise.
    This subclass returns real exceptions for known exception names.
    """
    _exceptions = FRAPPE_EXCEPTIONS
    
    def __getattr__(self, name):
        # Return real exception for known exception names FIRST
        if name in self._exceptions:
            return self._exceptions[name]
        # For everything else, use MagicMock's behavior
        return MagicMock.__getattr__(self, name)
    
    # Make sure these always return real classes
    @property
    def DoesNotExistError(self):
        return FRAPPE_EXCEPTIONS['DoesNotExistError']
    
    @property
    def ValidationError(self):
        return FRAPPE_EXCEPTIONS['ValidationError']
    
    @property
    def PermissionError(self):
        return FRAPPE_EXCEPTIONS['PermissionError']
    
    @property
    def NameError(self):
        return FRAPPE_EXCEPTIONS['NameError']
    
    @property
    def DuplicateEntryError(self):
        return FRAPPE_EXCEPTIONS['DuplicateEntryError']


# Monkey-patch unittest.mock.patch to use _FrappeMock for frappe patches
import unittest.mock
_original_patch = unittest.mock.patch

def _patch_with_frappe_mock(*args, **kwargs):
    """Custom patch that uses _FrappeMock for frappe-related patches"""
    # Check if any argument targets frappe
    target_is_frappe = any(
        (isinstance(a, str) and 'frappe' in a) for a in args
    )
    if target_is_frappe and 'spec' not in kwargs:
        # Use our custom mock class for frappe patches
        kwargs['Mock'] = _FrappeMock
    
    return _original_patch(*args, **kwargs)

# Replace the global patch function
import unittest.mock
unittest.mock.patch = _patch_with_frappe_mock


def _create_mock_frappe_module():
    """Create a comprehensive mock frappe module"""
    frappe_module = types.ModuleType("frappe")
    
    # Apply real exception classes FIRST - this is critical
    for name, exc_class in FRAPPE_EXCEPTIONS.items():
        setattr(frappe_module, name, exc_class)
    
    # Also set on frappe.exceptions submodule
    frappe_module.exceptions = types.ModuleType("frappe.exceptions")
    for name, exc_class in FRAPPE_EXCEPTIONS.items():
        setattr(frappe_module.exceptions, name, exc_class)
    
    # Mock frappe.session - THIS IS CRITICAL
    frappe_module.session = types.ModuleType("frappe.session")
    frappe_module.session.user = "Administrator"
    
    # Mock frappe.local
    frappe_module.local = types.ModuleType("frappe.local")
    frappe_module.local.session = types.ModuleType("frappe.local.session")
    frappe_module.local.session.user = "Administrator"
    frappe_module.local.site = "test.site"
    
    # Mock frappe.db - use a real module with MagicMock methods
    frappe_module.db = types.ModuleType("frappe.db")
    frappe_module.db.get_value = MagicMock(return_value=0)
    frappe_module.db.get_all = MagicMock(return_value=[])
    frappe_module.db.get_single_value = MagicMock(return_value=None)
    frappe_module.db.set_value = MagicMock()
    frappe_module.db.commit = MagicMock()
    frappe_module.db.rollback = MagicMock()
    frappe_module.db.exists = MagicMock(return_value=False)
    frappe_module.db.sql = MagicMock(return_value=[])
    
    # Mock frappe.utils - use real module type
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
    frappe_module.defaults = types.ModuleType("frappe.defaults")
    frappe_module.defaults.get_user_default = MagicMock(return_value="AMB-Wellness")
    frappe_module.defaults.get_default = MagicMock(return_value=None)
    
    # Mock other frappe functions
    frappe_module._dict = lambda x=None: dict(x) if x else {}
    frappe_module.as_json = lambda x: str(x)
    frappe_module._ = lambda x: x
    frappe_module.throw = MagicMock(side_effect=Exception)
    frappe_module.get_doc = MagicMock()
    frappe_module.new_doc = MagicMock()
    frappe_module.copy_doc = MagicMock()
    frappe_module.get_all = MagicMock(return_value=[])
    frappe_module.get_value = MagicMock()
    frappe_module.exists = MagicMock(return_value=False)
    frappe_module.log_error = MagicMock()
    frappe_module.publish_realtime = MagicMock()
    
    # frappe.whitelist decorator
    class _WhitelistDecorator:
        def __call__(self, fn=None, **kwargs):
            if fn is None:
                return lambda f: f
            return fn
    
    frappe_module.whitelist = _WhitelistDecorator()
    
    return frappe_module


# Create the mock frappe module once
MOCK_FRAPPE = _create_mock_frappe_module()


@pytest.fixture(autouse=True)
def setup_frappe_mock():
    """Setup frappe mock before each test - runs BEFORE the test"""
    # Clear raven_ai_agent modules
    for k in list(sys.modules):
        if k.startswith("raven_ai_agent"):
            del sys.modules[k]
    
    # Setup path
    if PROJECT_ROOT in sys.path:
        sys.path.remove(PROJECT_ROOT)
    sys.path.insert(0, PROJECT_ROOT)
    
    # Install our mock frappe module FIRST
    sys.modules["frappe"] = MOCK_FRAPPE
    
    # Also setup sub-modules
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
    frappe_defaults.get_default = MagicMock(return_value=None)
    sys.modules["frappe.defaults"] = frappe_defaults
    
    frappe_local = types.ModuleType("frappe.local")
    frappe_local.session = types.ModuleType("frappe.local.session")
    frappe_local.session.user = "Administrator"
    frappe_local.site = "test.site"
    sys.modules["frappe.local"] = frappe_local
    
    sys.modules["frappe.model"] = MagicMock()
    sys.modules["frappe.model.document"] = MagicMock()
    sys.modules["frappe.utils.data"] = MagicMock()
    sys.modules["frappe.exceptions"] = MOCK_FRAPPE.exceptions
    
    # ERPNext modules
    sys.modules["erpnext"] = MagicMock()
    sys.modules["erpnext.stock"] = MagicMock()
    sys.modules["erpnext.stock.doctype"] = MagicMock()
    sys.modules["erpnext.stock.doctype.stock_entry"] = MagicMock()
    sys.modules["erpnext.stock.doctype.stock_entry.stock_entry"] = MagicMock()
    sys.modules["erpnext.stock.doctype.delivery_note"] = MagicMock()
    sys.modules["erpnext.stock.doctype.delivery_note.delivery_note"] = MagicMock()
    sys.modules["erpnext.selling"] = MagicMock()
    sys.modules["erpnext.selling.doctype"] = MagicMock()
    sys.modules["erpnext.selling.doctype.sales_order"] = MagicMock()
    sys.modules["erpnext.selling.doctype.sales_order.sales_order"] = MagicMock()
    sys.modules["erpnext.selling.doctype.quotation"] = MagicMock()
    sys.modules["erpnext.selling.doctype.quotation.quotation"] = MagicMock()
    sys.modules["erpnext.controllers"] = MagicMock()
    sys.modules["erpnext.controllers.stock_controller"] = MagicMock()
    sys.modules["erpnext.manufacturing"] = MagicMock()
    sys.modules["erpnext.manufacturing.doctype"] = MagicMock()
    sys.modules["erpnext.manufacturing.doctype.work_order"] = MagicMock()
    sys.modules["erpnext.manufacturing.doctype.work_order.work_order"] = MagicMock()
    sys.modules["erpnext.manufacturing.doctype.bom"] = MagicMock()
    sys.modules["erpnext.manufacturing.doctype.bom.bom"] = MagicMock()
    sys.modules["erpnext.accounts"] = MagicMock()
    sys.modules["erpnext.accounts.doctype"] = MagicMock()
    sys.modules["erpnext.accounts.doctype.payment_entry"] = MagicMock()
    sys.modules["erpnext.accounts.doctype.payment_entry.payment_entry"] = MagicMock()
    sys.modules["erpnext.accounts.doctype.sales_invoice"] = MagicMock()
    sys.modules["erpnext.accounts.doctype.sales_invoice.sales_invoice"] = MagicMock()
    
    # Import raven_ai_agent to bind it to our mock
    import importlib
    importlib.import_module("raven_ai_agent")
    
    yield
    
    # Cleanup after test - restore frappe mock again in case patches messed with it
    sys.modules["frappe"] = MOCK_FRAPPE


@pytest.fixture(autouse=True)
def restore_frappe_exceptions():
    """Restore real exception classes after each test.
    
    When tests use @patch, it may replace frappe attributes with MagicMock.
    This fixture ensures exceptions are real classes.
    """
    yield
    
    # After test, restore exceptions to the mock frappe module
    frappe_mod = sys.modules.get("frappe")
    if frappe_mod:
        for name, exc_class in FRAPPE_EXCEPTIONS.items():
            setattr(frappe_mod, name, exc_class)
        
        # Also restore frappe.exceptions
        if hasattr(frappe_mod, 'exceptions'):
            frappe_mod.exceptions = MOCK_FRAPPE.exceptions
            for name, exc_class in FRAPPE_EXCEPTIONS.items():
                setattr(frappe_mod.exceptions, name, exc_class)
    
    # Also fix any raven_ai_agent agent modules that might have patched frappe
    for mod_name in list(sys.modules.keys()):
        if "raven_ai_agent" in mod_name and sys.modules[mod_name]:
            mod = sys.modules[mod_name]
            if hasattr(mod, 'frappe'):
                frappe_attr = getattr(mod, 'frappe', None)
                if frappe_attr is not None:
                    for name, exc_class in FRAPPE_EXCEPTIONS.items():
                        setattr(frappe_attr, name, exc_class)


def pytest_configure(config):
    """Initial setup - runs once before any tests"""
    sys.modules["frappe"] = MOCK_FRAPPE
    sys.modules["frappe.exceptions"] = MOCK_FRAPPE.exceptions
