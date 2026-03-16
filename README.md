# qBittorrent Helper

`qBittorrent Helper` 是一个面向运维场景的轻量脚本，用来定时检查 qBittorrent 中的任务并执行自动化清理。

它适合用 `cron` 每 5 分钟运行一次，而不是作为常驻进程部署。

## Features

- 基于 qBittorrent Web API 工作
- 短生命周期脚本，适合 `cron`
- 支持 JSON 配置
- 支持模块化扩展
- 支持全局 `dry_run`
- 自动轮转并清理旧日志
- 持久化模块状态，跨多次运行连续判断

当前内置模块：

- `stalled_cleanup`: 跟踪 `stalledDL` 的种子，达到阈值后打标签，再在更长时间后删除任务及文件

## Quick Start

### 1. Install

要求：

- Python 3.12+
- 已启用 qBittorrent Web UI

```bash
uv sync
```

### 2. Create config

```bash
cp config.example.json config.json
```

配置字段和默认示例请直接参考 `config.example.json`。

### 3. Run

```bash
uv run python main.py --config ./config.json
```

建议先使用 `dry_run: true` 观察日志，确认行为符合预期后再改为 `false`。

## How It Works

每次运行会：

1. 读取配置和状态文件
2. 登录 qBittorrent
3. 获取当前 torrent 列表
4. 执行已启用模块
5. 写入新的状态文件

`stalled_cleanup` 的默认策略：

- 第一次看到 `stalledDL` 时开始计时
- 达到 `candidate_seconds` 后打上 `candidate_tag`
- 达到 `delete_seconds` 后删除 torrent 和文件
- 如果任务恢复，则清除跟踪状态，并尝试移除标签

## Configuration

顶层配置分为四部分：

- `qbittorrent`: Web UI 地址、用户名、密码、请求超时
- `logging`: 日志路径、级别、轮转与保留策略
- `runtime`: 状态文件路径、全局 `dry_run`
- `modules`: 各模块开关与参数

`dry_run` 为全局行为开关。开启后会正常读取任务并记录计划动作，但不会真的修改 qBittorrent。

注意：

- 配置文件使用 JSON，不使用 `.env`
- 相对路径基于当前工作目录解析
- 生产环境建议对日志和状态文件使用绝对路径

## Deployment

推荐部署方式为 Linux `cron`：

```cron
*/5 * * * * cd /home/sylvan/qb-cleaner && /usr/bin/env uv run python main.py --config /home/sylvan/qb-cleaner/config.json
```

建议：

- 先用 `dry_run` 上线观察
- 确保运行用户对日志目录和状态文件目录有写权限
- 将 `candidate_seconds` 和 `delete_seconds` 设得保守一些

## Project Layout

```text
main.py
qb_helper/
  runner.py
  config.py
  client.py
  logging_utils.py
  state.py
  modules/
    stalled_cleanup.py
```

## Exit Codes

- `0`: 本次运行成功
- `1`: 配置错误、qBittorrent 通信失败、状态保存失败或模块执行失败

## License

如需开源发布，建议补充许可证信息。
