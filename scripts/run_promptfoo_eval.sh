#!/usr/bin/env bash
# Run Miho's offline promptfoo smoke evals without requiring live LLM keys.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_PATH="${1:-$REPO_ROOT/evals/promptfoo/miho-smoke.yaml}"

cd "$REPO_ROOT"

export NPM_CONFIG_LOGLEVEL="${NPM_CONFIG_LOGLEVEL:-error}"
export PROMPTFOO_DISABLE_TELEMETRY="${PROMPTFOO_DISABLE_TELEMETRY:-1}"
export PROMPTFOO_DISABLE_UPDATE="${PROMPTFOO_DISABLE_UPDATE:-1}"

exec npx --yes promptfoo@0.121.12 eval \
  --config "$CONFIG_PATH" \
  --no-cache
