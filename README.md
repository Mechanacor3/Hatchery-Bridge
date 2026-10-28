# Hatchery Bridge

Private MCP access to a Linux host through an authenticated OpenAI tunnel.
Provides durable shell jobs, bounded logs, workspace inspection, and SHA-guarded
file edits. Project-specific workflows belong in their own repositories.

## Install

Requires **Python 3.12 or newer**, user-level systemd, and an existing OpenAI
secure MCP tunnel with a `hatchery` profile. Docker is optional; commands can
use it when the service user has access.

Clone to `/ssd/workspace/hatchery-bridge`, then run as the service user:

```bash
cd /ssd/workspace/hatchery-bridge
PYTHON=python3.12 bash scripts/bootstrap.sh
bash scripts/doctor.sh
systemctl --user restart hatchery-mcp.service hatchery-bridge.service
```

Set `PYTHON` to another Python 3.12+ executable if needed. Bootstrap installs the
tested dependencies and user service units; it does not configure the tunnel or
create its credential. For services to run after logout, check
`loginctl show-user "$USER" -p Linger`.

| Location | Contents |
| --- | --- |
| `/ssd/workspace/hatchery-bridge` | Source checkout |
| `~/.local/share/hatchery-bridge/runtime` | Managed Python environment |
| `~/.local/state/hatchery-bridge` | Job records and logs |
| `~/.config/hatchery-bridge/tunnel-key` | Tunnel credential, loaded by systemd |

The `hatchery-bridge.service` tunnel forwards to `hatchery-mcp.service` at
`http://127.0.0.1:8765/mcp`. The tunnel health listener is `127.0.0.1:9088`.
Keep both listeners private. See [SECURITY.md](SECURITY.md) for the trust boundary.

## Operate

| Tool | Purpose |
| --- | --- |
| `status` | Host, disk/load, recent jobs. Call first. |
| `inspect_workspace` | Git, running Docker containers, and active jobs. |
| `run_command` | Start a noninteractive Bash job with a unique `request_id`. |
| `wait_job` | Wait up to 30 seconds and return newest output. |
| `get_job` | Read job state and bounded output; use `tail_bytes` for recent logs. |
| `cancel_job` | Request cancellation of the foreground process group. |
| `read_file` | Read a UTF-8 workspace file up to 256 KiB with its SHA256. |
| `write_file` | Atomically replace a file using the SHA from `read_file`. |

Example `run_command` arguments:

```json
{
  "command": "git diff --check && git status --short --branch",
  "request_id": "bridge-doc-check-001",
  "cwd": "hatchery-bridge",
  "timeout_seconds": 30
}
```

Reuse a request ID only to recover an uncertain response: it returns the original
job. Never automatically rerun an unresponsive command; inspect its effects first.
Use `wait_job` for short jobs and `get_job` with `tail_bytes` for longer ones.

Jobs survive client disconnects, but not host reboot or service shutdown. Each
retains up to 4 MiB of combined stdout/stderr. Terminal states are `succeeded`,
`failed`, `timed_out`, and `cancelled`. Stale `running` or `queued` jobs have
uncertain outcomes. Use systemd or Docker Compose for persistent services.

For edits, pass the exact SHA256 returned by `read_file` to `write_file`.
Use `missing` only to create a new file. For larger files, use bounded shell queries.
More operator examples: [operator skill](skills/hatchery-bridge/SKILL.md).

## Diagnose

```bash
bash scripts/doctor.sh
curl --fail http://127.0.0.1:9088/readyz
systemctl --user status hatchery-mcp.service hatchery-bridge.service --no-pager
journalctl _SYSTEMD_USER_UNIT=hatchery-mcp.service -n 60 --no-pager
journalctl _SYSTEMD_USER_UNIT=hatchery-bridge.service -n 60 --no-pager
```

Readiness checks the tunnel; confirm end-to-end access with a connected `status`
call. If only an old chat reports a protocol mismatch, reconnect the existing
plugin in a fresh chat before restarting healthy services.

## Develop

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-tested.txt
.venv/bin/python test_bridge.py
```

CI runs the suite on Python 3.12, covering job execution, deduplication,
timeout/cancellation, bounded output, file protections, MCP discovery, detached
jobs, and workspace inspection. Keep environments, Python caches, credentials,
and logs out of Git; `.gitignore` and CI guard against generated files.
