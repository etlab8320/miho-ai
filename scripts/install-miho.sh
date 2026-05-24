#!/usr/bin/env bash
set -euo pipefail

SKIP_SYNC=0
for arg in "$@"; do
  case "$arg" in
    --skip-sync)
      SKIP_SYNC=1
      ;;
    -h|--help)
      cat <<'USAGE'
Install the Miho AI CLI wrapper from this checkout.

Environment:
  MIHO_HOME       Miho data directory. Default: $HOME/.miho
  MIHO_BIN_DIR    CLI install directory. Default: $HOME/.local/bin
  MIHO_SYNC_ARGS  uv sync args. Default: --extra dev

Options:
  --skip-sync     Skip uv dependency sync, useful for tests.
USAGE
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 2
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MIHO_HOME="${MIHO_HOME:-$HOME/.miho}"
MIHO_BIN_DIR="${MIHO_BIN_DIR:-$HOME/.local/bin}"
MIHO_BIN="$MIHO_BIN_DIR/miho"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required to install Miho AI." >&2
  exit 1
fi

mkdir -p "$MIHO_HOME" "$MIHO_BIN_DIR"
chmod 700 "$MIHO_HOME"

if [[ "$SKIP_SYNC" != "1" ]]; then
  if [[ -n "${MIHO_SYNC_ARGS:-}" ]]; then
    read -r -a sync_args <<< "$MIHO_SYNC_ARGS"
  else
    sync_args=(--extra dev)
  fi
  (cd "$REPO_ROOT" && uv sync "${sync_args[@]}")
fi

if [[ -e "$MIHO_BIN" ]] && ! grep -q "Miho AI launcher" "$MIHO_BIN" 2>/dev/null; then
  backup="${MIHO_BIN}.backup.$(date +%Y%m%d%H%M%S)"
  mv "$MIHO_BIN" "$backup"
  echo "Existing miho command backed up to $backup"
fi

cat > "$MIHO_BIN" <<EOF
#!/usr/bin/env bash
# Miho AI launcher
set -euo pipefail
export MIHO_HOME="$MIHO_HOME"
export HERMES_BRAND="miho"
export HERMES_DEFAULT_SKIN="miho"
cd "$REPO_ROOT"
exec uv run miho "\$@"
EOF

chmod +x "$MIHO_BIN"

echo "Miho AI installed."
echo "Command: $MIHO_BIN"
echo "Home: $MIHO_HOME"
