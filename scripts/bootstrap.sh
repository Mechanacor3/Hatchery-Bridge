#!/usr/bin/env bash
set -euo pipefail

ROOT="${HATCHERY_BRIDGE_ROOT:-/ssd/workspace/hatchery-bridge}"
RUNTIME="${HATCHERY_RUNTIME:-$HOME/.local/share/hatchery-bridge/runtime}"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
PYTHON="${PYTHON:-/usr/bin/python3}"

[[ "$EUID" -ne 0 ]] || { echo 'Run as the service user, not root.' >&2; exit 1; }
[[ -f "$ROOT/server.py" ]] || { echo "Missing source checkout: $ROOT" >&2; exit 1; }
[[ -f "$ROOT/requirements-tested.txt" ]] || { echo 'Missing requirements-tested.txt' >&2; exit 1; }

printf 'Bootstrapping Hatchery Bridge\n'
printf '  source:  %s\n' "$ROOT"
printf '  runtime: %s\n' "$RUNTIME"

mkdir -p "$(dirname "$RUNTIME")" "$UNIT_DIR" "$HOME/.local/state/hatchery-bridge"
"$PYTHON" -m venv "$RUNTIME"
"$RUNTIME/bin/python" -m pip install --disable-pip-version-check --upgrade pip
"$RUNTIME/bin/python" -m pip install --disable-pip-version-check -r "$ROOT/requirements-tested.txt"

install -m 0644 "$ROOT/hatchery-mcp.service" "$UNIT_DIR/hatchery-mcp.service"
install -m 0644 "$ROOT/hatchery-bridge-user.service" "$UNIT_DIR/hatchery-bridge.service"
install -d -m 0755 "$UNIT_DIR/hatchery-bridge.service.d"
install -m 0644 "$ROOT/http-dependency.conf" "$UNIT_DIR/hatchery-bridge.service.d/http-dependency.conf"

systemctl --user daemon-reload
printf '\nBootstrap complete. Run:\n  %s/scripts/doctor.sh\n' "$ROOT"
printf 'Then start/restart with:\n  systemctl --user restart hatchery-mcp.service hatchery-bridge.service\n'
