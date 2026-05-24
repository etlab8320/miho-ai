#!/usr/bin/env python3
"""Miho AI console-script wrapper for the Hermes engine."""

try:
    import hermes_bootstrap  # noqa: F401
except ModuleNotFoundError:
    pass

import os
import sys
from pathlib import Path


def _is_version_argv(argv: list[str]) -> bool:
    return argv in (["--version"], ["-V"], ["version"])


def _configure_miho_runtime(*, create_home: bool) -> Path:
    os.environ.setdefault("HERMES_DEFAULT_SKIN", "miho")
    os.environ.setdefault("HERMES_BRAND", "miho")

    raw_home = os.environ.get("MIHO_HOME", "").strip()
    miho_home = Path(raw_home).expanduser() if raw_home else Path.home() / ".miho"
    os.environ["MIHO_HOME"] = str(miho_home)
    # Internal compatibility bridge for Hermes engine modules.
    os.environ["HERMES_HOME"] = str(miho_home)
    if create_home:
        miho_home.mkdir(parents=True, exist_ok=True)
    return miho_home


def _print_version_info() -> None:
    from hermes_cli import __release_date__, __version__
    from hermes_cli.brand import current_brand

    brand = current_brand()
    project_root = os.path.abspath(os.path.dirname(__file__))
    print(f"{brand.product_name} v{__version__} ({__release_date__})")
    print("Engine: Hermes Agent")
    print(f"Miho home: {os.environ['MIHO_HOME']}")
    print(f"Project: {project_root}")
    print(f"Python: {sys.version.split()[0]}")


def main() -> None:
    """Run Hermes through the Miho-branded entry point."""
    _configure_miho_runtime(create_home=not _is_version_argv(sys.argv[1:]))
    if _is_version_argv(sys.argv[1:]):
        _print_version_info()
        return

    from hermes_cli.main import main as hermes_main

    hermes_main()
