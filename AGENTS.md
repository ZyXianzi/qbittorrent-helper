# AGENTS.md

Always use Context7 when I need library/API documentation, code generation, setup or configuration steps without me having to explicitly ask.

## Project Purpose

This project is a qBittorrent helper designed to run as a short-lived scheduled job every 5 minutes.
Its responsibilities are operational and maintenance-oriented:

- inspect current torrents from qBittorrent
- run one or more helper modules
- log what happened
- persist lightweight module state between runs

The current built-in modules are:

- `stalled_cleanup`, which tracks torrents in `stalledDL`, tags them after a threshold, and deletes them after a longer threshold
- `disk_space_cleanup`, which deletes the largest completed torrent when free disk space falls below a configured threshold and then resumes errored downloads

## Runtime Model

- Entrypoint: `main.py`
- Main runner: `qb_helper/runner.py`
- Expected execution mode: short-lived process invoked by a scheduler such as `systemd timer` or cron
- Typical deployment command:
  - `/path/to/.venv/bin/python /path/to/main.py --config /path/to/config.toml`

This is not a daemon. Design changes should assume the process starts fresh on each run.

## Architecture

### High-level flow

1. `main.py` calls `qb_helper.runner.main()`
2. runner loads TOML config
3. runner initializes logging
4. runner loads persisted state from disk
5. runner logs into qBittorrent and fetches torrent list once
6. runner executes each enabled module
7. runner writes next state back to disk

### Package layout

- `main.py`
  - deployment entrypoint
- `qb_helper/runner.py`
  - orchestration, config loading, module execution, state save
- `qb_helper/config.py`
  - TOML config schema loading and validation
- `qb_helper/logging_utils.py`
  - shared logger setup and log retention handling
- `qb_helper/client.py`
  - qBittorrent Web API wrapper
- `qb_helper/models.py`
  - shared data models such as `Torrent`
- `qb_helper/state.py`
  - load/save JSON state file
- `qb_helper/modules/base.py`
  - module context and module result contracts
- `qb_helper/modules/stalled_cleanup.py`
  - first built-in module
- `qb_helper/modules/disk_space_cleanup.py`
  - disk pressure cleanup and download resume module
- `qb_helper/modules/__init__.py`
  - module registry

## Configuration

Configuration is TOML-based. The example template is `config.example.toml`.

Top-level sections:

- `qbittorrent`
  - server URL, credentials, request timeout
- `logging`
  - log file path, level, retention, rotation settings
- `runtime`
  - state file path, global `dry_run`
- `modules`
  - module-specific enable flag and options

Important notes:

- `.env` is no longer used.
- Runtime state remains JSON-based in the state file.
- Relative paths in config are resolved relative to the current working directory of the process.
- For scheduled deployments, prefer absolute paths or set the working directory explicitly before execution.

## Logging Conventions

The logger is shared, but each module writes with a module tag in the log line.

Current format:

`timestamp [LEVEL] [module_name] message`

Examples:

- `[app]` for runner-level messages
- `[stalled_cleanup]` for module messages

### Log retention

This project runs as a short-lived scheduled task, so retention cannot rely only on standard timed rotation behavior.

Current implementation:

- rotate logs on a timed basis
- proactively delete rotated log files older than the configured retention window on each run

If you change logging behavior, keep cron semantics in mind. This was added specifically to fix the earlier bug where old logs were not reliably cleaned up.

## State File Semantics

The state file is a JSON object keyed by module name.

Shape:

```json
{
  "stalled_cleanup": {
    "torrent_hash": {
      "name": "example",
      "first_seen_stalled": 1234567890
    }
  }
}
```

Rules:

- each module owns only its own subtree
- runner is responsible for loading and saving the whole state file
- modules should treat malformed or missing module state defensively

Do not make modules overwrite each other’s state.

## Module System

Modules are configured under `modules.<module_name>`.

Each module has:

- `enabled`
- `options`

Modules are registered manually in `qb_helper/modules/__init__.py`.

### Current module contract

Module input comes from `ModuleContext`:

- `client`
- `torrents`
- `dry_run`
- `logger`
- `now`

Module output is `ModuleResult(state=...)`.

### Expectations for new modules

When adding a new module:

1. create a file under `qb_helper/modules/`
2. parse and validate `options` inside that module
3. respect global `dry_run` for all side effects
4. log through the provided module logger
5. return only that module’s next state
6. add the module to `MODULE_REGISTRY`

### Error handling guidance

Prefer handling per-item operational failures inside the module so one bad torrent does not abort the whole module.

Only let errors escape to runner when the module cannot proceed at all because of invalid config or a broader unrecoverable condition.

## qBittorrent Client Guidance

`qb_helper/client.py` is intentionally small and focused on the Web API calls used by modules.

When extending it:

- keep methods thin
- return normalized project models where useful
- do not mix module policy into the client

The client should remain an integration boundary, not a decision layer.

## Dry Run Policy

`runtime.dry_run` is global.

That means:

- all side-effecting modules are expected to honor it
- dry run should log intended actions instead of mutating qBittorrent

Do not introduce module-specific dry-run behavior unless there is a clear operational need. The current design intentionally keeps dry-run semantics simple and global.

## Deployment Assumptions

- Python is typically provided from `.venv/bin/python`
- execution is via a Linux scheduler, with `systemd timer` preferred and cron still supported
- the process is expected to finish quickly
- qBittorrent connectivity errors should fail the run clearly in logs

Recommended `systemd` deployment shape:

```ini
[Service]
Type=oneshot
WorkingDirectory=/home/sylvan/qb-cleaner
ExecStart=/home/sylvan/qb-cleaner/.venv/bin/python /home/sylvan/qb-cleaner/main.py --config /home/sylvan/qb-cleaner/config.toml

[Timer]
OnCalendar=*:0/5
Persistent=true
```

## Practical Rules For Future Changes

- preserve the short-lived cron-job model
- avoid adding unnecessary framework complexity
- keep config validation explicit and easy to trace
- prefer module isolation over clever abstractions
- keep logs operationally useful
- maintain backward awareness for deployment paths and state transitions
- when code changes affect architecture, config, module contracts, runtime behavior, or deployment assumptions, update this `AGENTS.md` in the same change

## Known History / Migration Notes

- the project started as a single-file script
- environment-variable config was replaced by TOML config
- entrypoint was changed from `qb_stalled_cleaner.py` to `main.py`
- log retention was fixed to work correctly for cron-style short executions

If future refactors touch any of those areas, validate migration impact carefully because this project is operational tooling rather than a user-facing app.
