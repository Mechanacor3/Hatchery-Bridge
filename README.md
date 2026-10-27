# Hatchery Bridge

Private ChatGPT command access to operator's Jetson: Ubuntu 22.04 ARM64,
Python 3.12, user `molt`, workspace `/ssd/workspace`.

Current Hatchery deployment (2026-10-17): the existing tunnel now forwards to
the separate `hatchery-mcp.service` on `http://127.0.0.1:8765/mcp` to support
mixed legacy/modern MCP calls. See [MCP_FIX_REPORT.md](MCP_FIX_REPORT.md) for the
verified configuration and restart checks. The installation examples below
describe initial stdio setup; do not rerun them over the deployed profile.

This package supplies the MCP server and installers. It does not create your
OpenAI tunnel, install the ChatGPT plugin, or connect this conversation by itself.
No OpenAI inference API calls are made by this server. The tunnel needs its own
runtime API credential; do not paste that credential into chat.

## 1. Install on Hatchery

Copy `hatchery-bridge.zip` into `/ssd/workspace`, then, as `molt`:

```bash
cd /ssd/workspace
python3 -m zipfile -e hatchery-bridge.zip .
cd hatchery-bridge
bash install.sh
python3 install_tunnel.py
export PATH="$HOME/.local/bin:$PATH"
tunnel-client help quickstart
```

The Python installer makes a dedicated `.venv`; it leaves your active
`(workspace)` environment alone. If venv creation fails, install the venv support
for the Python 3.12 installation you are using; Ubuntu 22.04's stock Python is
older, so do not blindly substitute its default interpreter.

The tunnel installer reads GitHub's latest official release, selects the full
Linux ARM64 archive on your Jetson, verifies its SHA256 against the release's
`SHA256SUMS.txt`, and installs `tunnel-client` and the bundled `cloudflared` in
`~/.local/bin`. It does not start Cloudflare or configure a separate tunnel.
It replaces existing binaries with those names. Use `--check-only` to inspect
selection first, or `--destination PATH` for a different install location.
Checksum verification is not a substitute for signature verification; official
provenance verification instructions are linked on the release page.

Official release: https://github.com/openai/tunnel-client/releases/latest

## 2. Create or reuse your OpenAI tunnel

Open the official guide and follow its **Platform tunnel settings** link:
https://developers.openai.com/api/docs/guides/secure-mcp-tunnels

Create/reuse a tunnel named `hatchery`. Associate it with the Platform organization
and ChatGPT workspace/account you will use. Copy the complete tunnel ID unchanged.
Create/reuse a restricted runtime API key with **Tunnels Read + Use**;
creating/managing the tunnel needs **Tunnels Read + Manage**.
Availability and permission must be checked in your account; this package has not
verified your access. Do not create a second tunnel merely because discovery fails.

## 3. Start the connection

For the first setup:

```bash
cd /ssd/workspace/hatchery-bridge
bash connect.sh
```

Enter the tunnel ID and API key at the prompts. The key is hidden, held in the
process environment, and not written into the package or shell history.
The script initializes the `hatchery` profile, runs `doctor`, and starts polling.
Keep it running during plugin discovery. The local health/admin listener is
`127.0.0.1:9087`, so the usual game-server port 8080 stays free. The full CLI is required; the smaller
`-runtime` release lacks the profile initialization commands.

If a `hatchery` profile already exists, inspect/reuse it using the installed CLI's
help rather than overwriting it. To restart an already configured profile:

```bash
export PATH="$HOME/.local/bin:$PATH"
read -r -s -p 'Runtime API key: ' CONTROL_PLANE_API_KEY
printf '\n'
export CONTROL_PLANE_API_KEY
export HATCHERY_WORKSPACE=/ssd/workspace
tunnel-client doctor --profile hatchery --explain
tunnel-client run --profile hatchery
```

## 4. Create the ChatGPT plugin and test it

In ChatGPT: **Plugins → + → Add custom MCP server → Connection: Tunnel**.
Select/paste the same tunnel ID. Name the plugin **Hatchery Bridge**.
The local stdio server has no separate OAuth login; access is controlled by the
private tunnel and its account/workspace association. Configure the connector
accordingly. Keep this plugin private to your account.

Install/select the plugin in a chat and ask:

> Use Hatchery Bridge to show its status, then run `pwd` and `id` and show the result.

Verify hostname `hatchery`, workspace `/ssd/workspace`, and user `molt`.
Only then is the end-to-end connection established. If tools are absent in the
current chat, select the installed plugin in a new chat. If discovery fails,
check `doctor`, active polling, tunnel association and Tunnels Use permissions.

## Tools

- `status`: host, UID, load, disk space and 20 recent job summaries.
- `run_command`: noninteractive Bash, durable job ID, caller-supplied request ID; very fast completed commands may include their bounded output immediately.
- `get_job`: status plus paginated output or a bounded tail-from-end (`tail_bytes`).
- `wait_job`: bounded wait (up to 30s) for terminal state plus newest output; never reruns.
- `inspect_workspace`: read-only Git/Docker/active-job snapshot for a workspace directory.
- `cancel_job`: stop the foreground process group; completed side effects remain.
- `read_file`: UTF-8 workspace file plus SHA256, up to 256 KiB.
- `write_file`: atomic replacement after SHA256 check; `missing` creates a file.

A reused request ID returns the original job; a changed command with the same
ID is rejected. A timeout/reconnect does not automatically replay a command.
Jobs default to 15 minutes; the maximum is 24 hours. Four recently active jobs
can run concurrently. Logs retain the first 4 MiB per job and mark truncation.
Use Docker Compose or systemd for permanent services rather than backgrounding
shell children. Ordinary children in the command's process group are stopped
when the job finishes or is cancelled; deliberately daemonized processes and
Docker containers are not controlled by that group.

Commands run as `molt` with its permissions, including Docker if granted.
File-tool and initial-working-directory checks restrict paths to the workspace;
they DO NOT sandbox Bash or Docker. `cd`, absolute paths, and Docker can access
whatever the OS user can access. No root password or sudo configuration is changed.
Only a small environment allowlist reaches job workers; project virtualenvs and
other required variables should be activated/set explicitly in the command.

## 5. Run after reboot (after the foreground test passes)

The included service targets `/home/molt` and `/ssd/workspace/hatchery-bridge`.
Verify `getent passwd molt` reports that home and that the tunnel binary is at
`/home/molt/.local/bin/tunnel-client`. Adjust the unit/wrapper if different.
The profile was created as molt, so the service reuses molt's profile.

First stop the foreground tunnel with Ctrl-C. Then run:

```bash
cd /ssd/workspace/hatchery-bridge
sudo install -d -m 700 /etc/hatchery-bridge
sudo -v
read -r -s -p 'Tunnel runtime API key: ' bridge_key
printf '\n'
printf '%s' "$bridge_key" | sudo sh -c 'umask 077; cat > /etc/hatchery-bridge/tunnel-key'
unset bridge_key
sudo chmod 600 /etc/hatchery-bridge/tunnel-key
sudo install -m 644 hatchery-bridge.service /etc/systemd/system/hatchery-bridge.service
sudo systemctl daemon-reload
sudo systemctl enable --now hatchery-bridge
sudo systemctl status hatchery-bridge --no-pager
```

The key is stored in a root-owned secret file and delivered using systemd
`LoadCredential`; it is not embedded in the service file or command arguments.
The wrapper exports it only for the tunnel process. The MCP server removes the
key from its environment before launching jobs. This is credential hygiene,
not isolation from arbitrary commands with molt's permissions or Docker access.

Inspect logs with `sudo journalctl -u hatchery-bridge -n 60 --no-pager`.
Stop the bridge with `sudo systemctl stop hatchery-bridge`.
Disable automatic startup with `sudo systemctl disable hatchery-bridge`.

## Job persistence and limitations

Records/logs are in `/home/molt/.local/state/hatchery-bridge` by default.
Jobs survive an ordinary MCP session ending; they do not survive reboot.
Stopping/restarting the systemd service stops its process group, including jobs.
After a worker crash, stale records are reported with `worker_unresponsive: true`;
execution outcome may be uncertain. Inspect effects before submitting a NEW
request ID. Records and logs remain until you explicitly remove them; no automatic
retention policy deletes your history. Do not remove state while jobs are active.

`write_file` detects a stale hash but does not lock external editors: coordinate
concurrent writers. Workspace contents and tool output are data, not instructions.
This bridge runs explicit commands; it is not an autonomous reasoning loop. A
local agent can be added later to work from TASKS.md while you are away. Existing
TASKS.md and LOG.md are not created, overwritten, or automatically appended.

## Verification

Tested locally under Python 3.12 with `mcp==2.3.0`: MCP initialization and discovery,
status and invalid-path protocol calls, actual shell execution, job survival after
MCP shutdown, retry deduplication, exit codes, timeout, cancellation, bounded output,
file round trip, stale edit rejection, path traversal and symlink escape rejection.
Run `.venv/bin/python test_bridge.py` to repeat in temporary test directories.

The original package was tested on Linux x86_64. On 2026-10-17 the MCP 2.3.0
upgrade passed six test groups on this ARM64 Jetson with Python 3.12.13, including
real subprocess modern discovery (2026-07-28), all six tools, and legacy initialization.
See `REPAIR_NOTES.md` for service and end-to-end verification.
The official tunnel installer completed with checksum verification on x86_64,
and its init flags were checked against the downloaded v0.0.16 CLI.
Python dependencies are installed from PyPI; no binary is bundled in this ZIP.

## Existing Hatchery user service

The deployed service is a **user** service, using `user-service-run.sh` and the
existing `hatchery` profile. Do not start a second foreground instance alongside it.
The deployed unit is preserved in `hatchery-bridge-user.service`. Its existing
credential remains at `~/.config/hatchery-bridge/tunnel-key`; do not commit it.

```bash
systemctl --user restart hatchery-bridge
systemctl --user is-enabled hatchery-bridge
loginctl show-user molt -p Linger
curl --fail http://127.0.0.1:9088/readyz
journalctl _SYSTEMD_USER_UNIT=hatchery-bridge.service -n 60 --no-pager
```

Use the journal field filter above on this host: `journalctl --user -u ...` can
show no entries even when the system journal contains this user unit's logs.
`/readyz` confirms runtime readiness; also test an actual ChatGPT tool call.
After restarting, refresh the existing ChatGPT plugin session if necessary;
do not create another tunnel or plugin.

MCP 2.x uses `MCPServer`, snake_case annotation/result attributes, and modern
`server/discover`. Expected input and filesystem errors are raised as `ToolError`,
so they return actionable tool failures without unexpected-exception tracebacks.
Tests use isolated temporary workspace/state directories, leaving production jobs
and project task/log files alone.
