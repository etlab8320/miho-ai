#!/usr/bin/env python3
"""Unattended entry point for the Governance OS Self-Harness autopilot.

Registered as a ``no_agent`` cron job by
``plugins.governance_os.self_harness_loop.register_self_harness_cron``. Its stdout
is delivered verbatim as the job output, so it prints a compact JSON summary of
the cycle (candidates activated / rolled back / held).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running as a bare script from ~/.miho/scripts or the repo.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def main() -> int:
    from plugins.governance_os.self_harness_loop import run_self_harness_autopilot

    summary = run_self_harness_autopilot()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    # Surface a non-zero exit only when the loop itself errored on candidates.
    return 1 if summary.get("errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
