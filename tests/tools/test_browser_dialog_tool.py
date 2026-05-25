from __future__ import annotations

import builtins
import importlib
import sys


def test_browser_dialog_tool_import_does_not_require_cdp_supervisor(monkeypatch):
    """Gateway startup should not warn just because optional CDP deps are absent."""

    real_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "tools.browser_supervisor":
            raise ModuleNotFoundError("No module named 'websockets'")
        return real_import(name, globals, locals, fromlist, level)

    sys.modules.pop("tools.browser_dialog_tool", None)
    monkeypatch.setattr(builtins, "__import__", guarded_import)

    module = importlib.import_module("tools.browser_dialog_tool")

    assert callable(module.browser_dialog)
