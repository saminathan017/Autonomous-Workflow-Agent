from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

_configured = False


def configure_logging(log_level: str = "INFO") -> None:
    global _configured
    if _configured:
        return

    logger.remove()

    logger.add(
        sys.stderr,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> — "
            "<level>{message}</level>"
        ),
        level=log_level,
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    log_dir = Path(__file__).parent.parent.parent / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.add(
        str(log_dir / "app_{time:YYYY-MM-DD}.log"),
        rotation="00:00",
        retention="30 days",
        compression="gz",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{line} — {message}",
        backtrace=True,
    )

    _configured = True


def setup_logging(log_level: str = "INFO", **_) -> None:
    configure_logging(log_level)


def get_logger(name: str):
    return logger.bind(name=name)
