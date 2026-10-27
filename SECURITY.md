# Security model

Hatchery Bridge is a private remote-operations bridge, not a sandbox.

## Trust boundary

- The MCP HTTP endpoint binds to loopback only.
- Remote access is through the authenticated OpenAI secure tunnel.
- Shell commands execute as the service user with that user's real OS permissions.
- Docker access, when granted to the service user, is effectively host-level authority and should be treated accordingly.
- File tools are workspace-scoped and SHA-guarded; shell commands are not filesystem-sandboxed.

## Credentials

Tunnel credentials must never be committed, placed in commands, or written to logs. The deployed user service reads the credential from `~/.config/hatchery-bridge/tunnel-key` through systemd credential loading. Worker environments deliberately exclude the control-plane credential.

## Runtime separation

The source checkout contains no runtime environment or mutable state. Python dependencies live under `~/.local/share/hatchery-bridge/runtime`; job metadata and logs live under `~/.local/state/hatchery-bridge`.

## Reporting

This repository is currently a personal infrastructure project. Do not open a public issue containing credentials, host secrets, private tunnel identifiers, or sensitive command output.
