#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
export PATH="$HOME/.local/bin:$PATH"
command -v tunnel-client >/dev/null || { echo 'Install the official Linux ARM64 full tunnel-client first; see README.md.' >&2; exit 1; }
[[ -x .venv/bin/python ]] || { echo 'Run bash install.sh first.' >&2; exit 1; }
read -r -p 'Tunnel ID: ' bridge_tunnel_id
[[ -n "$bridge_tunnel_id" ]] || exit 1
read -r -s -p 'Tunnel runtime API key (hidden): ' CONTROL_PLANE_API_KEY
printf '\n'
export CONTROL_PLANE_API_KEY
export HATCHERY_WORKSPACE=/ssd/workspace
# A fixed profile name allows recovery without creating a second tunnel.
# Inspect existing profile first; do not silently overwrite it on later runs.
tunnel-client init --sample sample_mcp_stdio_local --profile hatchery --force \
  --health-listen-addr 127.0.0.1:9087 \
  --tunnel-id "$bridge_tunnel_id" --mcp-command "$PWD/.venv/bin/python $PWD/server.py"
tunnel-client doctor --profile hatchery --explain
exec tunnel-client run --profile hatchery
