"""Regression tests for _apply_profile_override MIHO_HOME guard (issue #22502).

When MIHO_HOME is set to the miho root (e.g. systemd hardcodes
MIHO_HOME=/root/.miho), _apply_profile_override must still read
active_profile and update MIHO_HOME to the profile directory.

When MIHO_HOME is already a profile directory (.../profiles/<name>),
_apply_profile_override must trust it and return without re-reading
active_profile (child-process inheritance contract).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


def _run_apply_profile_override(
    tmp_path, monkeypatch, *, miho_home: str | None, active_profile: str | None,
    argv: list[str] | None = None,
):
    """Run _apply_profile_override in isolation.

    Returns the value of os.environ["MIHO_HOME"] after the call,
    or None if unset.
    """
    miho_root = tmp_path / ".miho"
    miho_root.mkdir(parents=True, exist_ok=True)

    if active_profile is not None:
        (miho_root / "active_profile").write_text(active_profile)

    if active_profile and active_profile != "default":
        (miho_root / "profiles" / active_profile).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    if miho_home is not None:
        monkeypatch.setenv("MIHO_HOME", miho_home)
    else:
        monkeypatch.delenv("MIHO_HOME", raising=False)

    monkeypatch.setattr(sys, "argv", argv or ["miho", "gateway", "start"])

    from miho_cli.main import _apply_profile_override
    _apply_profile_override()

    return os.environ.get("MIHO_HOME")


class TestApplyProfileOverrideMihoHomeGuard:
    """Regression guard for issue #22502.

    Verifies that MIHO_HOME pointing to the miho root does NOT suppress
    the active_profile check, while MIHO_HOME already pointing to a
    profile directory IS trusted as-is.
    """

    def test_miho_home_at_root_with_active_profile_is_redirected(
        self, tmp_path, monkeypatch
    ):
        """MIHO_HOME=/root/.miho + active_profile=coder must redirect
        MIHO_HOME to .../profiles/coder.

        Bug scenario from #22502: systemd sets MIHO_HOME to the miho root
        and the user switches to a profile via `miho profile use`.
        Before the fix, the guard returned early and active_profile was ignored.
        """
        miho_root = tmp_path / ".miho"
        miho_root.mkdir(parents=True, exist_ok=True)

        result = _run_apply_profile_override(
            tmp_path,
            monkeypatch,
            miho_home=str(miho_root),
            active_profile="coder",
        )

        assert result is not None, "MIHO_HOME must be set after profile redirect"
        assert "profiles" in result, (
            f"Expected MIHO_HOME to point into profiles/ dir, got: {result!r}"
        )
        assert result.endswith("coder"), (
            f"Expected MIHO_HOME to end with 'coder', got: {result!r}"
        )

    def test_miho_home_already_profile_dir_is_trusted(self, tmp_path, monkeypatch):
        """MIHO_HOME=.../profiles/coder must not be overridden even when
        active_profile says something different.

        Preserves the child-process inheritance contract: a subprocess spawned
        with MIHO_HOME already set to a specific profile must stay in that
        profile.
        """
        miho_root = tmp_path / ".miho"
        profile_dir = miho_root / "profiles" / "coder"
        profile_dir.mkdir(parents=True, exist_ok=True)

        (miho_root / "active_profile").write_text("other")

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setenv("MIHO_HOME", str(profile_dir))
        monkeypatch.setattr(sys, "argv", ["miho", "gateway", "start"])

        from miho_cli.main import _apply_profile_override
        _apply_profile_override()

        assert os.environ.get("MIHO_HOME") == str(profile_dir), (
            "MIHO_HOME must remain unchanged when already pointing to a profile dir"
        )

    def test_miho_home_unset_reads_active_profile(self, tmp_path, monkeypatch):
        """Classic case: MIHO_HOME unset + active_profile=coder must set
        MIHO_HOME to the profile directory (existing behaviour must not regress).
        """
        result = _run_apply_profile_override(
            tmp_path,
            monkeypatch,
            miho_home=None,
            active_profile="coder",
        )

        assert result is not None
        assert "coder" in result

    def test_miho_home_unset_default_profile_no_redirect(self, tmp_path, monkeypatch):
        """active_profile=default must not redirect MIHO_HOME."""
        miho_root = tmp_path / ".miho"
        miho_root.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.delenv("MIHO_HOME", raising=False)
        monkeypatch.setattr(sys, "argv", ["miho", "gateway", "start"])
        (miho_root / "active_profile").write_text("default")

        from miho_cli.main import _apply_profile_override
        _apply_profile_override()

        assert os.environ.get("MIHO_HOME") is None
