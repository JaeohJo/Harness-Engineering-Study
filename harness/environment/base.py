"""워크스페이스 실행 환경 인터페이스 정의 모듈."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional


class BaseEnvironment(ABC):
    """태스크별 격리된 실행 환경의 수명주기를 정의하는 추상 인터페이스.

    Python 컨텍스트 매니저(`with env:`) 프로토콜을 지원하여 자원의 안전한 할당과 해제를 보장합니다.
    """

    @abstractmethod
    def setup(self) -> Path:
        """워크스페이스를 격리 초기화하고 작업 루트 디렉터리 경로를 반환합니다."""
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """격리된 워크스페이스를 정리하고 임시 자원을 안전하게 반환합니다."""
        pass

    @abstractmethod
    def get_diff(self) -> str:
        """해당 워크스페이스에서 발생한 모든 코드 변경사항(Unified Diff)을 반환합니다."""
        pass

    @abstractmethod
    def get_modified_files(self) -> List[str]:
        """수정, 생성, 삭제된 모든 파일의 상대 경로 목록을 반환합니다."""
        pass

    @abstractmethod
    def apply_patch(self, patch_content: str) -> None:
        """워크스페이스에 Unified Diff 패치를 적용합니다."""
        pass

    @abstractmethod
    def reset_baseline(self) -> None:
        """사전 파일 주입이나 설정 완료 후, 변경사항 측정의 기준선(baseline)을 현재 상태로 재설정합니다."""
        pass

    def __enter__(self) -> BaseEnvironment:
        self.setup()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.cleanup()
