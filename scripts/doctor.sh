#!/usr/bin/env bash
set -euo pipefail

ROOT="${HATCHERY_BRIDGE_ROOT:-/ssd/workspace/hatchery-bridge}"
WORKSPACE="${HATCHERY_WORKSPACE:-/ssd/workspace}"
RUNTIME="${HATCHERY_RUNTIME:-$HOME/.local/share/hatchery-bridge/runtime}"
STATE="${HATCHERY_STATE:-$HOME/.local/state/hatchery-bridge}"

ok()   { printf '  ✓ %s\n' "$*"; }
warn() { printf '  ! %s\n' "$*"; }
fail() { printf '  ✗ %s\n' "$*"; return 1; }

errors=0
printf 'Hatchery Bridge doctor\n\n'

[[ -d "$ROOT/.git" ]] && ok "source checkout: $ROOT" || { fail "missing source checkout: $ROOT"; errors=$((errors+1)); }
[[ -d "$WORKSPACE" ]] && ok "workspace: $WORKSPACE" || { fail "missing workspace: $WORKSPACE"; errors=$((errors+1)); }
[[ -x "$RUNTIME/bin/python" ]] && ok "runtime python: $RUNTIME/bin/python" || { fail "runtime not bootstrapped: $RUNTIME"; errors=$((errors+1)); }
[[ -d "$STATE" ]] && ok "state directory: $STATE" || warn "state directory will be created on first start: $STATE"

if command -v docker >/dev/null 2>&1; then
  docker info >/dev/null 2>&1 && ok 'Docker available to service user' || warn 'Docker CLI exists but daemon is unavailable to this user'
else
  warn 'Docker CLI not installed (optional)'
fi

if command -v systemctl >/dev/null 2>&1; then
  for unit in hatchery-mcp.service hatchery-bridge.service; do
    if systemctl --user is-active --quiet "$unit"; then
      ok "$unit active"
    else
      warn "$unit not active"
    fi
  done
fi

if [[ -x "$RUNTIME/bin/python" ]]; then
  "$RUNTIME/bin/python" - <<'PY' >/dev/null 2>&1 && ok 'Python dependencies import cleanly' || { fail 'Python dependency import failed'; errors=$((errors+1)); }
import mcp
PY
fi

if [[ -f "$ROOT/server.py" ]]; then
  /usr/bin/python3 -m py_compile "$ROOT/server.py" >/dev/null 2>&1 && ok 'server.py syntax' || { fail 'server.py syntax error'; errors=$((errors+1)); }
fi

printf '\n'
if (( errors )); then
  printf 'Doctor found %d blocking issue(s).\n' "$errors"
  exit 1
fi
printf 'Everything essential looks healthy.\n'
