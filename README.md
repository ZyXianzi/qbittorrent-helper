# qBittorrent Helper

Lightweight qBittorrent maintenance helper for short-lived scheduled runs.

[中文说明](#中文说明)

## Overview

qBittorrent Helper is a small Python tool for operational automation around qBittorrent.
It is designed to run as a short-lived job every few minutes through `systemd timer` or `cron`, rather than as a long-running daemon.

Each run:

1. loads TOML configuration
2. loads persisted module state from disk
3. logs into qBittorrent Web API
4. fetches the current torrent list once
5. executes enabled helper modules
6. writes next state back to disk

The built-in modules today are:

- `stalled_cleanup`: tracks torrents in `stalledDL`, tags them after a threshold, and deletes them after a longer threshold
- `value_retention_cleanup`: scores completed torrents by recent upload yield, activity, size, and cohort policy to keep high-value seeds longer and delete low-value seeds proactively or under disk pressure

## Features

- Short-lived process model suitable for `systemd timer` or `cron`
- TOML-based configuration
- Lightweight JSON state persisted across runs
- Modular helper architecture
- Global `dry_run` mode for safe rollout
- Shared structured logging with module tags
- Timed log rotation plus proactive retention cleanup for cron-style execution

## Why This Exists

qBittorrent exposes useful torrent states, but many maintenance policies are environment-specific.
This project provides a simple place to implement those policies without turning them into a permanent service.

The focus is operational reliability:

- minimal moving parts
- explicit config validation
- defensive state handling
- scheduler-friendly execution model

## Safety Model

This project can perform destructive actions, including deleting torrents and downloaded files.

Recommended rollout:

1. start with `runtime.dry_run = true`
2. review logs for several scheduler cycles
3. confirm your thresholds and tag behavior
4. switch `dry_run` to `false` only after validation

## Requirements

- Python 3.12+
- qBittorrent with Web UI enabled
- Network access from this job to the qBittorrent Web API

## Installation

```bash
uv sync
```

If you are not using `uv`, install dependencies from `pyproject.toml` with your preferred workflow.

For local development checks, install dev tools and git hooks once per clone:

```bash
uv sync --dev
uv run pre-commit install --install-hooks
```

This repository uses:

- `pre-commit` on staged files for `ruff-check` and `ruff-format`
- `pre-commit` on staged Python files for `ty check`
- `pre-push` for the full `pytest` unit test suite

To run everything manually:

```bash
uv run pre-commit run --all-files
uv run ty check main.py qb_helper
```

Local hooks operate on the files staged for the current commit.
The installed git hooks include both `pre-commit` and `pre-push`.
GitHub Actions runs changed-file quality checks plus the full unit test suite on every push and pull request.

## Quick Start

1. Create a config file:

```bash
cp config.example.toml config.toml
```

2. Edit `config.toml` for your environment.

3. Run once manually:

```bash
uv run python main.py --config ./config.toml
```

4. Review logs before enabling scheduled execution.

## Configuration

Top-level config sections:

- `qbittorrent`: server URL, credentials, request timeout
- `logging`: log file path, level, rotation, retention
- `runtime`: state file path and global `dry_run`
- `modules`: per-module enable flag and options

Important notes:

- Configuration format is TOML
- Runtime state is stored as JSON
- Relative paths are resolved from the process working directory
- For scheduled deployments, absolute paths are strongly recommended

## Built-in Module

### `stalled_cleanup`

Tracks torrents whose qBittorrent state is `stalledDL`.

Default behavior:

- start tracking when a torrent is first seen in `stalledDL`
- add a candidate tag after `candidate_seconds`
- delete the torrent and files after `delete_seconds`
- clear state if the torrent recovers or disappears
- remove the candidate tag if a tracked torrent recovers

### `value_retention_cleanup`

Scores completed torrents with one shared policy engine so the same decision model can be used for:

- routine post-seeding cleanup after a cohort's base seed time
- disk pressure cleanup when free space falls below a threshold
- automatic extension of high-value torrents up to a configured max seed time

Behavior:

- classifies each completed torrent into the first matching policy
- records lightweight hourly upload snapshots in module state
- computes value from recent upload per GiB, 24h upload per GiB, current upload speed, idle time, and size penalty
- protects torrents by tag, category, or tracker substring
- deletes low-value torrents after their base seed time
- when free space is low, deletes the lowest-value torrents until the target free-space level is estimated to be reached
- optionally resumes errored downloads after cleanup

Recommended use:

- use this as the primary retention and low-space cleanup module for upload-focused boxes with small disks

Value scoring model:

- the module only evaluates completed torrents
- each torrent uses the first matching policy from `policies`; if none match, `default_policy` is used
- the module stores hourly `uploaded` snapshots and calculates upload deltas over `recent_window_hours` and `long_window_hours`
- protection rules are checked before deletion; matching `protected_tags`, `protected_categories`, or `protected_tracker_contains` prevent automatic deletion

Current score formula:

```text
score =
  policy.priority
  + score_weights.recent_upload_per_gib * recent_uploaded_per_gib
  + score_weights.long_upload_per_gib * long_uploaded_per_gib
  + score_weights.current_upspeed_mib * current_upspeed_mib
  - score_weights.idle_hours * idle_hours
  - score_weights.size_root * sqrt(size_gib)
```

Term definitions:

- `policy.priority`: cohort prior configured per policy; use this to favor higher-value groups such as adult large packs
- `recent_uploaded_per_gib`: uploaded bytes during `recent_window_hours`, converted to GiB and divided by torrent size in GiB
- `long_uploaded_per_gib`: uploaded bytes during `long_window_hours`, converted to GiB and divided by torrent size in GiB
- `current_upspeed_mib`: current qBittorrent upload speed in MiB/s
- `idle_hours`: hours since `last_activity`
- `sqrt(size_gib)`: size penalty that grows with torrent size, but less aggressively than a linear penalty

Retention and deletion flow:

- if `delete_low_value_after_base_seed = true`, torrents that have reached `base_seed_hours` are eligible for deletion when their score is below `min_score_to_keep`
- torrents that have reached `max_seed_hours` are eligible for deletion regardless of score
- if free space is below `min_free_space_gb`, the module keeps deleting from lowest-value to highest-value until the estimated free space reaches `target_free_space_gb` or `max_deletions_per_run` is hit
- deletion priority is ordered as:
  1. torrents beyond `max_seed_hours`
  2. torrents beyond `base_seed_hours` and below `min_score_to_keep`
  3. remaining unprotected torrents during disk pressure
- within the same priority tier, lower score is deleted first; if scores are similar, larger and older seeds are favored for deletion

Operational notes:

- the first few runs have limited history, so the 6h and 24h upload terms become more informative after the module has been running for a while
- for reliable cohort selection, prefer qBittorrent `category` for major groups and reserve tags for overlays such as `manual-keep`
- if other automation already deletes torrents after a fixed time, disable that policy so this module can make the final retention decision

## Execution Model

This is not a daemon.
The process is expected to start fresh, do its work quickly, persist state, and exit.

Typical deployment command:

```bash
/path/to/.venv/bin/python /path/to/main.py --config /path/to/config.toml
```

## Deployment

`systemd timer` is the recommended deployment model.
Example unit files are included in:

- `deploy/systemd/qb-helper.service.example`
- `deploy/systemd/qb-helper.timer.example`

Typical service shape:

```ini
[Service]
Type=oneshot
WorkingDirectory=/home/youruser/qbittorrent-helper
ExecStart=/home/youruser/qbittorrent-helper/.venv/bin/python /home/youruser/qbittorrent-helper/main.py --config /home/youruser/qbittorrent-helper/config.toml
```

Typical timer shape:

```ini
[Timer]
OnCalendar=*:0/5
Persistent=true
```

Why `systemd timer` over `cron`:

- explicit `WorkingDirectory`
- clearer execution logs with `journalctl`
- better service ownership and environment control
- missed runs can be replayed with `Persistent=true`

`cron` is still supported if it better matches your environment.

## Project Layout

```text
main.py
qb_helper/
  runner.py
  config.py
  client.py
  logging_utils.py
  state.py
  models.py
  modules/
    __init__.py
    base.py
    stalled_cleanup.py
    value_retention_cleanup.py
deploy/systemd/
config.example.toml
```

## Logging

Log lines include a module tag:

```text
timestamp [LEVEL] [module_name] message
```

Examples:

- `[app]` for runner-level logs
- `[stalled_cleanup]` for module logs

Log retention is enforced proactively on each run so old rotated files are cleaned up even though the process is short-lived.

## Exit Codes

- `0`: run completed successfully
- `1`: config load failure, qBittorrent communication failure, module failure, or state save failure

## Roadmap Ideas

- additional maintenance modules
- more module-level safety checks
- tests for config parsing and module state transitions

## Contributing

Issues and pull requests are welcome.

If you plan to contribute a new module:

- keep the short-lived scheduler model intact
- validate module options explicitly
- respect global `dry_run`
- keep module state isolated to its own subtree
- avoid pushing policy into the qBittorrent client layer

Contributors should install local hooks before committing:

```bash
uv sync --dev
uv run pre-commit install --install-hooks
```

Hook policy:

- `pre-commit` runs `ruff-check`, `ruff-format`, and `ty check` on staged files
- `pre-push` runs the full `pytest` suite
- CI reruns changed-file checks plus full unit tests on every push and pull request

## License

MIT

---

## 中文说明

`qBittorrent Helper` 是一个面向运维场景的轻量工具，用于定时检查 qBittorrent 任务并执行自动化维护动作。

它的设计目标不是常驻运行，而是作为一个短生命周期任务，由 `systemd timer` 或 `cron` 每隔几分钟拉起一次。

每次运行会：

1. 读取 TOML 配置
2. 读取磁盘上的模块状态
3. 登录 qBittorrent Web API
4. 获取当前 torrent 列表
5. 执行已启用模块
6. 写回新的状态

当前内置模块：

- `stalled_cleanup`：跟踪 `stalledDL` 状态的种子，达到阈值后打标签，再在更长时间后删除任务及文件
- `value_retention_cleanup`：对已完成任务按近期上传收益、活跃度、体积和 cohort 策略打分，在日常保种和磁盘压力清理时统一决定保留或删除

### 功能特点

- 适合 `systemd timer` 或 `cron` 的短生命周期执行模式
- 使用 TOML 配置
- 使用轻量 JSON 持久化模块状态
- 支持模块化扩展
- 提供全局 `dry_run` 安全开关
- 统一日志格式，并带模块标识
- 支持日志轮转和基于保留时间的主动清理

### 安全建议

这个项目可能执行破坏性操作，包括删除 torrent 和本地文件。

建议上线流程：

1. 先设置 `runtime.dry_run = true`
2. 连续观察多个调度周期的日志
3. 确认阈值、标签和行为符合预期
4. 再切换为 `false`

### 运行要求

- Python 3.12+
- 已启用 qBittorrent Web UI
- 当前任务所在机器能访问 qBittorrent Web API

### 快速开始

安装依赖：

```bash
uv sync
```

复制配置：

```bash
cp config.example.toml config.toml
```

手动运行一次：

```bash
uv run python main.py --config ./config.toml
```

建议先观察日志，再启用定时调度。

### 配置结构

顶层配置包括：

- `qbittorrent`：服务地址、用户名、密码、超时
- `logging`：日志路径、级别、轮转、保留策略
- `runtime`：状态文件路径和全局 `dry_run`
- `modules`：模块开关和模块参数

补充说明：

- 配置文件格式为 TOML
- 运行时状态文件格式为 JSON
- 相对路径基于进程工作目录解析
- 在定时任务部署场景下，强烈建议使用绝对路径

### 部署建议

推荐使用 `systemd timer` 部署，仓库中已经提供示例文件：

- `deploy/systemd/qb-helper.service.example`
- `deploy/systemd/qb-helper.timer.example`

这个项目不是 daemon，而是一次性完成任务后退出的脚本。

### 日志格式

日志格式如下：

```text
timestamp [LEVEL] [module_name] message
```

例如：

- `[app]` 表示 runner 层日志
- `[stalled_cleanup]` 表示模块日志

### 退出码

- `0`：执行成功
- `1`：配置错误、qBittorrent 通信失败、模块失败或状态保存失败

### 许可证

MIT
