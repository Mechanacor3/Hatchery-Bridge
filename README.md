# Hatchery Bridge

A small, private MCP bridge for operating the Hatchery Jetson from ChatGPT.

Hatchery Bridge intentionally does **not** try to become an orchestration framework. It provides a tight remote-operations substrate: durable shell jobs, bounded output, safe file replacement, compact workspace inspection, and a private tunnel into the Jetson. Project-specific logic stays in the project repositories.

## Design

```text
ChatGPT
  │
  │ private OpenAI tunnel
  ▼
hatchery-bridge.service       tunnel-client
  │
  ▼
127.0.0.1:8765/mcp
  │
  ▼
hatchery-mcp.service          Python MCP server
  │
  ├── durable shell jobs
  ├── bounded job logs
  ├── workspace inspection
  └── SHA-guarded file edits
```

The source checkout is disposable. Runtime dependencies and mutable state live outside Git:

```text
/ssd/workspace/hatchery-bridge/                 source
~/.local/share/hatchery-bridge/runtime/         Python runtime
~/.local/state/hatchery-bridge/                 jobs + logs
~/.config/hatchery-bridge/tunnel-key            tunnel credential
```

## Tool surface

| Tool | Purpose |
| --- | --- |
| `status` | Host, disk/load, recent jobs. Call this first. |
| `inspect_workspace` | Read-only Git, Docker, and active-job snapshot. |
| `run_command` | Start a durable noninteractive Bash command. |
| `wait_job` | Wait up to 30 seconds for terminal state and return newest output. |
| `get_job` | Read job state and paged or tail-from-end output. |
| `cancel_job` | Request cancellation of the foreground process group. |
| `read_file` | Read a UTF-8 workspace file with SHA256. |
| `write_file` | Atomically replace a file only when its expected SHA matches. |

That is the whole API on purpose.

## Bootstrap

Requirements:

- Linux host
- Python 3.12 recommended
- user-level systemd
- Docker optional, but available to commands when the service user has access
- an existing OpenAI secure MCP tunnel

Clone to the expected location, then bootstrap as the service user:

```bash
cd /ssd/workspace/hatchery-bridge
bash scripts/bootstrap.sh
bash scripts/doctor.sh
```

The bootstrap creates the managed runtime at `~/.local/share/hatchery-bridge/runtime`, installs the tested dependency set, and installs the user service units. It does not create or overwrite your tunnel credential.

Start or restart the services:

```bash
systemctl --user restart hatchery-mcp.service hatchery-bridge.service
systemctl --user status hatchery-mcp.service hatchery-bridge.service --no-pager
```

For an always-on user service, verify lingering is enabled:

```bash
loginctl show-user "$USER" -p Linger
```

## Tunnel

The deployed tunnel profile is named `hatchery`. The tunnel forwards to the loopback MCP endpoint at:

```text
http://127.0.0.1:8765/mcp
```

The tunnel runtime credential belongs in:

```text
~/.config/hatchery-bridge/tunnel-key
```

Do not put the credential in Git, shell commands, logs, chat messages, or service arguments. The service uses systemd credential loading.

The tunnel health listener is loopback-only at `127.0.0.1:9088`.

## Normal operator workflow

Start a Hatchery work pass with `status`, then use `inspect_workspace` for the target repository. Prefer one semantic request ID per intended command.

Example `run_command` arguments:

```json
{
  "command": "git diff --check && git status --short --branch",
  "request_id": "fishbowl-doc-check-20261027",
  "cwd": "ai-fishbowl",
  "timeout_seconds": 30
}
```

For a short job, use `wait_job` once:

```json
{
  "job_id": "<job id>",
  "wait_seconds": 10,
  "tail_bytes": 16384
}
```

For a long-running job, use `get_job` with `tail_bytes` when you only need the newest output. Use byte offsets only when you actually need to page the full retained log.

A request ID is an idempotency key for the **intent**, not a polling token. Reuse it only to recover an uncertain response. Never automatically resubmit a command whose worker appears unresponsive; inspect its effects first.

## File edits

For normal UTF-8 files up to 256 KiB:

1. `read_file`
2. retain the returned SHA256
3. `write_file` with that exact SHA

This prevents stale blind overwrites. `missing` is accepted only when intentionally creating a new file.

For larger files, use a targeted bounded shell query rather than dumping the file into MCP output.

## Security model

Hatchery Bridge is a **private remote shell with guardrails**, not a sandbox.

Workspace path checks constrain the file tools and initial command directory. They do not constrain what Bash or Docker can access afterward. Commands run with the service user's real permissions, including Docker access when granted.

The bridge deliberately strips the tunnel control-plane credential before launching workers. This is credential hygiene, not privilege separation from code already running as the same OS user.

The MCP service is loopback-only and its user service applies conservative systemd hardening. Do not expose port 8765 publicly.

## Jobs

Jobs are durable across MCP client disconnects and retain up to 4 MiB of combined stdout/stderr. They do not survive a host reboot or service shutdown.

Terminal states are:

```text
succeeded
failed
timed_out
cancelled
```

An apparently stale `running` or `queued` job has an uncertain outcome. Inspect before creating a new request ID.

## Development

Run the test suite:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-tested.txt
.venv/bin/python test_bridge.py
```

`.venv`, Python caches, credentials, local logs, and build output are forbidden from Git by `.gitignore`; CI also verifies that they are not tracked.

The test suite covers command execution, request-ID deduplication, timeout/cancellation, output caps, SHA-guarded file edits, path escapes, modern MCP discovery, detached jobs, job tails, and workspace inspection.

## Diagnostics

```bash
bash scripts/doctor.sh
curl --fail http://127.0.0.1:9088/readyz
journalctl _SYSTEMD_USER_UNIT=hatchery-mcp.service -n 60 --no-pager
journalctl _SYSTEMD_USER_UNIT=hatchery-bridge.service -n 60 --no-pager
```

`doctor.sh` is intentionally read-only. It checks the source checkout, workspace, managed runtime, state directory, Docker availability, systemd service state, dependency imports, and server syntax.

## Why it stays small

The bridge should make remote work reliable without absorbing project semantics. Fishbowl resets, model admission, deployment choreography, security policy, and similar domain workflows belong in their own repositories. Hatchery Bridge should remain boring, auditable infrastructure.
