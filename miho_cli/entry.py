"""Miho AI console-script entry point."""

from __future__ import annotations

try:
    import miho_bootstrap  # noqa: F401
except ModuleNotFoundError:
    pass

import os
import sys
from pathlib import Path


def _is_version_argv(argv: list[str]) -> bool:
    return argv in (["--version"], ["-V"], ["version"])


def _configure_miho_runtime(*, create_home: bool) -> Path:
    os.environ["MIHO_RUNTIME"] = "1"
    os.environ.setdefault("MIHO_BRAND", "miho")

    raw_home = os.environ.get("MIHO_HOME", "").strip()
    miho_home = Path(raw_home).expanduser() if raw_home else Path.home() / ".miho"
    os.environ["MIHO_HOME"] = str(miho_home)
    if create_home:
        miho_home.mkdir(parents=True, exist_ok=True)
    return miho_home


def _print_version_info() -> None:
    from miho_cli import __release_date__, __version__
    from miho_cli.brand import current_brand

    brand = current_brand()
    project_root = os.path.abspath(Path(__file__).resolve().parents[1])
    print(f"{brand.product_name} v{__version__} ({__release_date__})")
    print("Runtime: Miho native")
    print(f"Miho home: {os.environ['MIHO_HOME']}")
    print(f"Project: {project_root}")
    print(f"Python: {sys.version.split()[0]}")


def main() -> None:
    """Run Miho AI."""
    _configure_miho_runtime(create_home=not _is_version_argv(sys.argv[1:]))
    if _is_version_argv(sys.argv[1:]):
        _print_version_info()
        return

    from miho_cli.main import main as engine_main

    engine_main()
