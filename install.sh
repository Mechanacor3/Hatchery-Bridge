#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ "$EUID" = 0 ]]; then
  echo 'Run this installer as molt, without sudo.' >&2
  exit 1
fi
python3 -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10+ required"'
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
printf '\nInstalled MCP server in %s\nNext: follow README.md to connect the tunnel.\n' "$PWD"
