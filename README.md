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
- `disk_space_cleanup`: deletes the largest completed torrent when free disk space drops below a configured threshold, then resumes errored downloads
- `tag_share_limit`: applies configured `seedingTimeLimit` values to torrents whose tags match configured rules

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
- `pre-commit` for `ty check`

To run everything manually:

```bash
uv run pre-commit run --all-files
uv run ty check main.py qb_helper
```

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

### `disk_space_cleanup`

Monitors qBittorrent reported free disk space.

Default example behavior:

- when free disk space drops below `min_free_space_gb`
- delete the largest completed torrent and its files
- refresh the torrent list
- resume any incomplete torrents currently in `error`

This module is stateless. It is intended for environments where low disk space can leave downloads stuck in an error state until enough space is reclaimed.

### `tag_share_limit`

Applies a configured `seedingTimeLimit` to torrents when their tags match configured rules.

Behavior:

- configure a mapping of `tag -> seedingTimeLimit in minutes`
- if a torrent matches one configured tag, use that rule
- if a torrent matches multiple configured tags, use the shortest configured limit
- if the torrent already has the desired `seedingTimeLimit`, no API call is made
- this module is stateless

Example:

```toml
[modules.tag_share_limit]
enabled = true

[modules.tag_share_limit.options.tag_seeding_time_limit_minutes]
keep-1d = 1440
keep-7d = 10080
"保种 30 天" = 43200
```

Notes:

- TOML supports UTF-8, so Chinese tag names can be written directly
- if a tag contains spaces or special characters, quote the key
- the tag text must exactly match the tag configured in qBittorrent

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
    disk_space_cleanup.py
    stalled_cleanup.py
    tag_share_limit.py
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

- `pre-commit` runs `ruff-check`, `ruff-format`, and `ty check`
- CI reruns the same checks on pull requests and pushes to `main`

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
- `disk_space_cleanup`：磁盘剩余空间低于阈值时，删除体积最大的已完成任务，然后恢复错误中的下载任务
- `tag_share_limit`：当任务命中指定标签时，按配置设置 `seedingTimeLimit`

### `tag_share_limit` 配置说明

这个模块用于按照 tag 给任务设置保种时间上限。

行为规则：

- 配置形式是 `tag -> seedingTimeLimit（分钟）`
- 如果一个任务只命中一个已配置 tag，就使用该规则
- 如果一个任务同时命中多个已配置 tag，就取时间最短的那条规则
- 如果当前任务的 `seedingTimeLimit` 已经是目标值，则不会重复调用 API
- 该模块不需要持久化状态

示例：

```toml
[modules.tag_share_limit]
enabled = true

[modules.tag_share_limit.options.tag_seeding_time_limit_minutes]
保种1天 = 1440
保种7天 = 10080
"保种 30 天" = 43200
```

说明：

- TOML 支持 UTF-8，所以中文 tag 可以直接写
- 如果 tag 含有空格或特殊字符，建议给 key 加引号
- 配置中的 tag 名必须和 qBittorrent 里的 tag 完全一致

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
