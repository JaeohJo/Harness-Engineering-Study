"""Antigravity 하네스 시스템의 구조화된 컬러 콘솔 로깅 모듈.

rich 라이브러리를 활용하여 타임스탬프, 컬러 마크업 및 가독성 높은 로그를 출력합니다.
"""

from __future__ import annotations

import logging
from rich.console import Console
from rich.logging import RichHandler

console = Console()


def setup_logger(name: str = "agy_harness", level: int = logging.INFO) -> logging.Logger:
    """Rich 기반의 포맷팅된 로거 인스턴스를 초기화하고 반환합니다."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 중복 핸들러 등록 방지
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
