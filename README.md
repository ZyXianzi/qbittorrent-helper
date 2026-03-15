## qBittorrent helper

工程化后的定时任务入口是 `main.py`。

配置方式改为 JSON：

```bash
cp config.example.json config.json
python main.py --config ./config.json
```

当前内置模块：

- `stalled_cleanup`: 清理长时间 `stalledDL` 的种子，可单独启停。

日志会按小时轮转，并在每次运行时主动清理 24 小时前的历史日志文件。
