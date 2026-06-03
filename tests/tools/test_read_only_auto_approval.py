"""Read-only gateway commands should not wait on approval buttons."""

import os

from tools import approval as approval_module


SESSION_KEY = "test-read-only-auto-approval"


def _reset_approval_state():
    approval_module._gateway_queues.clear()
    approval_module._gateway_notify_cbs.clear()
    approval_module._session_approved.clear()
    approval_module._permanent_approved.clear()
    approval_module._pending.clear()


def _set_gateway_env(monkeypatch):
    monkeypatch.delenv("MIHO_YOLO_MODE", raising=False)
    monkeypatch.delenv("MIHO_INTERACTIVE", raising=False)
    monkeypatch.setenv("MIHO_GATEWAY_SESSION", "1")
    monkeypatch.setenv("MIHO_SESSION_KEY", SESSION_KEY)
    monkeypatch.setattr(approval_module, "_get_approval_mode", lambda: "manual")


class TestReadOnlyAutoApproval:
    def setup_method(self):
        _reset_approval_state()

    def teardown_method(self):
        _reset_approval_state()
        os.environ.pop("MIHO_GATEWAY_SESSION", None)
        os.environ.pop("MIHO_SESSION_KEY", None)

    def test_python_read_script_does_not_request_gateway_approval(self, monkeypatch):
        _set_gateway_env(monkeypatch)
        command = "python3 <<'PY'\nimport json\nprint(json.dumps({'ok': True}))\nPY"

        result = approval_module.check_all_command_guards(command, "local")

        assert result["approved"] is True
        assert result.get("status") != "pending_approval"
        assert SESSION_KEY not in approval_module._pending

    def test_shell_read_command_does_not_request_gateway_approval(self, monkeypatch):
        _set_gateway_env(monkeypatch)
        command = "bash -lc 'date +%F && ls /tmp >/dev/null'"

        result = approval_module.check_all_command_guards(command, "local")

        assert result["approved"] is True
        assert result.get("status") != "pending_approval"

    def test_temp_image_renderer_does_not_request_gateway_approval(self, monkeypatch):
        _set_gateway_env(monkeypatch)
        command = (
            "python3 <<'PY'\n"
            "import matplotlib.pyplot as plt\n"
            "plt.plot([1, 2, 3])\n"
            "plt.savefig('/tmp/miho-card.png')\n"
            "PY"
        )

        result = approval_module.check_all_command_guards(command, "local")

        assert result["approved"] is True
        assert result.get("status") != "pending_approval"

    def test_sensitive_python_write_still_requests_gateway_approval(self, monkeypatch):
        _set_gateway_env(monkeypatch)
        command = (
            "python3 <<'PY'\n"
            "from pathlib import Path\n"
            "Path('/etc/sudoers').write_text('bad')\n"
            "PY"
        )

        result = approval_module.check_all_command_guards(command, "local")

        assert result["approved"] is False
        assert result.get("status") == "pending_approval"
        assert SESSION_KEY in approval_module._pending

    def test_destructive_sql_still_requests_gateway_approval(self, monkeypatch):
        _set_gateway_env(monkeypatch)
        command = "python3 <<'PY'\nprint('DROP TABLE students')\nPY"

        result = approval_module.check_all_command_guards(command, "local")

        assert result["approved"] is False
        assert result.get("status") == "pending_approval"
