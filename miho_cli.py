#!/usr/bin/env python3
"""Compatibility entry point for the Miho CLI console script."""

# IMPORTANT: miho_bootstrap must be the very first import — UTF-8 stdio
# on Windows. No-op on POSIX. See miho_bootstrap.py for full rationale.
try:
    import miho_bootstrap  # noqa: F401
except ModuleNotFoundError:
    pass

from miho_cli.main import main


if __name__ == "__main__":
    main()
