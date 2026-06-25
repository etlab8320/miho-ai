#!/usr/bin/env python3
"""Clean stale Miho media-cache files."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_manager():
    module_path = REPO_ROOT / "gateway" / "media_cache_manager.py"
    spec = importlib.util.spec_from_file_location("miho_media_cache_manager", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load media cache manager: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _retention_days() -> int:
    raw = os.getenv("MIHO_MEDIA_CACHE_RETENTION_DAYS", "14").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 14


def main() -> int:
    dry_run = os.getenv("MIHO_MEDIA_CACHE_CLEANUP_DRY_RUN", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    manager = _load_manager()
    summary = manager.cleanup_media_cache(retention_days=_retention_days(), dry_run=dry_run)
    print(manager.format_cleanup_summary(summary))
    print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))
    return 0 if not summary.errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
