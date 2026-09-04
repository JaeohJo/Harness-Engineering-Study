"""Structured and formatted logging for the Antigravity Harness system."""

from __future__ import annotations

import logging
import sys
from typing import Optional
from rich.console import Console
from rich.logging import RichHandler

console = Console()


def setup_logger(name: str = "agy_harness", level: int = logging.INFO) -> logging.Logger:
    """Configures and returns a rich logger instance."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid duplicate handlers if setup_logger is called multiple times
    if not logger.handlers:
        handler = RichHandler(
            console=console,
            show_time=True,
            show_path=False,
            rich_tracebacks=True,
            markup=True,
        )
        handler.setLevel(level)
        formatter = logging.Formatter("%(message)s", datefmt="[%X]")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    logger.propagate = False
    return logger


logger = setup_logger()
