# Hatchery Bridge operator skill

Use Hatchery Bridge as a small remote-execution substrate. Prefer its read-only inspection/wait helpers over repeated shell calls; keep project-specific orchestration in the project repository.

## Start a work pass

Call `status` first when beginning a new Hatchery operation. Then use `inspect_workspace` for the target repository instead of separately shelling out to `git status`, `git rev-parse`, and `docker ps`.

Example arguments:
```json
{"cwd":"ai-fishbowl"}
```

`inspect_workspace` is read-only and returns Git HEAD/branch/status, running Docker summaries, and active Bridge jobs. It does not replace project-specific health or isolation checks.

## Run a command and wait efficiently

Use one unique semantic `request_id` for each intended mutation or command. Reuse it only to recover a response whose outcome is uncertain.

```json
{"command":"git diff --check && git status --short --branch","request_id":"fishbowl-doc-check-20261027","cwd":"ai-fishbowl","timeout_seconds":30}
```

For commands expected to finish within a few seconds, call `wait_job` rather than repeatedly polling `get_job`:

```json
{"job_id":"<job id>","wait_seconds":10,"tail_bytes":16384}
```

`wait_job` waits at most 30 seconds, returns early when terminal, and never retries or reruns the command.

## Follow a longer job

Use `get_job` with `tail_bytes` when the useful question is “what happened most recently?” This avoids manually tracking byte offsets:

```json
{"job_id":"<job id>","tail_bytes":16384}
```

Use `offset` + `max_bytes` only when paging the complete retained output is actually necessary.

## Files and large ledgers

Use `read_file` for UTF-8 workspace files up to 256 KiB instead of `cat`/large `tail` commands. Before editing, retain its SHA256 and pass that exact value to `write_file`; use `missing` only when intentionally creating a new file.

For files larger than 256 KiB, use a targeted bounded shell query (`grep`, `sed`, or a small script) rather than dumping a large tail into job output.

## Safety and scope

The Bridge's workspace checks are not a Bash or Docker sandbox. Commands run with the service user's permissions. Do not put credentials in commands or output. Do not automatically rerun an unresponsive job: inspect its effects first. Use Docker Compose/systemd for durable services rather than backgrounding shell children.
