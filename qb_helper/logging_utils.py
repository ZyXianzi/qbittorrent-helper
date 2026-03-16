from __future__ import annotations

import logging
import sys
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from qb_helper.config import LoggingConfig


class ModuleNameFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "module_name"):
            record.module_name = "app"
        return True


class RecentTimedRotatingFileHandler(TimedRotatingFileHandler):
    def __init__(
        self,
        filename: str,
        retention_seconds: int,
        when: str,
        interval: int,
        encoding: str,
    ) -> None:
        self.retention_seconds = retention_seconds
        super().__init__(
            filename=filename,
            when=when,
            interval=interval,
            backupCount=0,
            encoding=encoding,
        )
        self._purge_expired_files()

    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self._purge_expired_files()

    def doRollover(self) -> None:
        super().doRollover()
        self._purge_expired_files()

    def _purge_expired_files(self) -> None:
        cutoff = time.time() - self.retention_seconds
        base_path = Path(self.baseFilename)
        for candidate in base_path.parent.glob(f"{base_path.name}*"):
            if candidate == base_path:
                continue
            try:
                if candidate.is_file() and candidate.stat().st_mtime < cutoff:
                    candidate.unlink()
            except OSError:
                continue


def setup_logging(config: LoggingConfig) -> logging.Logger:
    logger = logging.getLogger("qb_helper")
    logger.setLevel(getattr(logging, config.level, logging.INFO))
    logger.handlers.clear()
    logger.filters.clear()
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(module_name)s] %(message)s"
    )
    module_filter = ModuleNameFilter()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(module_filter)
    logger.addHandler(console_handler)

    config.file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RecentTimedRotatingFileHandler(
        filename=str(config.file),
        retention_seconds=max(config.retention_hours, 1) * 3600,
        when=config.rotate_when,
        interval=max(config.rotate_interval, 1),
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(module_filter)
    logger.addHandler(file_handler)

    return logger


def get_module_logger(
    base_logger: logging.Logger, module_name: str
) -> logging.LoggerAdapter:
    return logging.LoggerAdapter(base_logger, {"module_name": module_name})
