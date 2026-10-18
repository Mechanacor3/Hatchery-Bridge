#!/usr/bin/env bash
set -euo pipefail
export PATH="/home/molt/.local/bin:/usr/local/bin:/usr/bin:/bin"
export HATCHERY_WORKSPACE=/ssd/workspace
CONTROL_PLANE_API_KEY="$(cat "$CREDENTIALS_DIRECTORY/tunnel-key")"
export CONTROL_PLANE_API_KEY
exec /home/molt/.local/bin/tunnel-client run --profile hatchery --health.listen-addr 127.0.0.1:9088
