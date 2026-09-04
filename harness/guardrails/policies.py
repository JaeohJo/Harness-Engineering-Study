"""에이전트 안전 가드레일 및 셸 명령어 보안 정책 모듈.

파괴적 파일시스템 명령어, 포크밤, 외부 리버스 셸 탈취, .git 디렉터리 훼손 등
위험한 명령어 패턴을 정규식으로 감지하고 차단하는 정책 규칙을 정의합니다.
"""

from __future__ import annotations

import re
from typing import List
from pydantic import BaseModel, Field


# 기본 차단 명령어 정규식 목록 (안전한 실험 환경 보장)
DEFAULT_BLOCKED_COMMAND_PATTERNS = [
    r"\brm\s+[^;\|]*-[a-zA-Z0-9_-]*r[a-zA-Z0-9_-]*[^;\|]*/(?:\s|$)",    # 루트 디렉터리 재귀 삭제 (rm -rf /)
    r"\brm\s+[^;\|]*-[a-zA-Z0-9_-]*r[a-zA-Z0-9_-]*[^;\|]*\.\./(?:\s|$)", # 상위 디렉터리 탈출 삭제 (rm -rf ../)
    r"\brm\s+[^;\|]*-[a-zA-Z0-9_-]*r[a-zA-Z0-9_-]*[^;\|]*\.git(?:\s|$|/)", # Git 메타데이터 파괴 (rm -rf .git)
    r"\bmkfs\b",                                                         # 파일시스템 포맷 명령어
    r"\bdd\s+if=.*of=/dev/",                                             # 블록 디바이스 덮어쓰기
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:",                        # Bash 포크밤
    r"\bchmod\s+-R\s+777\s+/(?:\s|$)",                                  # 루트 권한 전면 개방
    r"\bcurl\s+.*\|\s*(?:ba)?sh(?:\s|$)",                               # 인터넷 스크립트 직접 파이프 실행
    r"\bwget\s+.*\|\s*(?:ba)?sh(?:\s|$)",
    r"\b(?:nc|netcat)\s+-e\b",                                          # 넷캣 리버스 셸
]


class SecurityPolicy(BaseModel):
    """도구 실행 제약 및 보안 검사 규칙 설정."""
    enabled: bool = Field(default=True, description="보안 가드레일 활성화 여부")
    blocked_command_patterns: List[str] = Field(
        default_factory=lambda: list(DEFAULT_BLOCKED_COMMAND_PATTERNS),
        description="즉시 차단해야 하는 위험 셸 명령어의 정규식 패턴 목록",
    )
    allow_git_write: bool = Field(default=False, description="Git 내부 명령 직접 쓰기 허용 여부")
    max_command_timeout: int = Field(default=60, description="단일 도구 실행 최대 허용 시간(초)")

    def check_command(self, command_line: str) -> tuple[bool, str]:
        """주어진 명령어가 안전 정책을 통과하는지 검사합니다.

        Returns:
            (is_safe, reason): 안전 여부 및 차단 사유
        """
        if not self.enabled:
            return True, "보안 정책 검사가 비활성화되어 있습니다."

        for pattern in self.blocked_command_patterns:
            if re.search(pattern, command_line, flags=re.IGNORECASE):
                return False, f"보안 정책 위반: 차단된 패턴 '{pattern}'과 일치하는 위험 명령어가 감지되었습니다."

        return True, "보안 검사를 정상적으로 통과했습니다."
