"""Pytest-style conftest plus side-effect import hooks so the secrets tests
can run via ``python -m`` outside a Frappe runtime."""
import sys
import types


def _install_stubs():
    if "frappe" not in sys.modules:
        fake = types.ModuleType("frappe")
        fake.conf = {}
        fake.logger = lambda: types.SimpleNamespace(debug=lambda *a, **kw: None)
        pw_mod = types.ModuleType("frappe.utils.password")
        _STORE = {}

        def get_decrypted_password(doctype, name, fieldname, raise_exception=True):
            return _STORE.get((doctype, fieldname))

        pw_mod.get_decrypted_password = get_decrypted_password
        pw_mod._store = _STORE
        utils_mod = types.ModuleType("frappe.utils")
        utils_mod.password = pw_mod
        fake.utils = utils_mod
        sys.modules["frappe"] = fake
        sys.modules["frappe.utils"] = utils_mod
        sys.modules["frappe.utils.password"] = pw_mod

    for _opt in ("openai", "anthropic", "httpx"):
        if _opt not in sys.modules:
            _stub = types.ModuleType(_opt)
            if _opt == "openai":
                _stub.OpenAI = lambda **kw: None
            if _opt == "anthropic":
                _stub.Anthropic = lambda **kw: None
            sys.modules[_opt] = _stub


_install_stubs()
