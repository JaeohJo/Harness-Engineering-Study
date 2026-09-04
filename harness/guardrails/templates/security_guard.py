#!/usr/bin/env python3
"""Antigravity CLI 자동 주입 보안 가드레일 인터셉터 스크립트.

에이전트가 도구(run_command 등)를 실행하기 직전에 PreToolUse 훅으로 호출되어,
명령어가 위험한 패턴(루트 삭제, 포크밤, 리버스 셸 등)에 해당하는지 검사하고 차단합니다.
"""

import json
import re
import sys
from pathlib import Path

# 기본 차단 패턴 (폴백용)
DEFAULT_PATTERNS = [
    r"\brm\s+[^;\|]*-[a-zA-Z0-9_-]*r[a-zA-Z0-9_-]*[^;\|]*/(?:\s|$)",
    r"\brm\s+[^;\|]*-[a-zA-Z0-9_-]*r[a-zA-Z0-9_-]*[^;\|]*\.\./(?:\s|$)",
    r"\brm\s+[^;\|]*-[a-zA-Z0-9_-]*r[a-zA-Z0-9_-]*[^;\|]*\.git(?:\s|$|/)",
    r"\bmkfs\b",
    r"\bdd\s+if=.*of=/dev/",
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:",
    r"\bchmod\s+-R\s+777\s+/(?:\s|$)",
    r"\bcurl\s+.*\|\s*(?:ba)?sh(?:\s|$)",
    r"\bwget\s+.*\|\s*(?:ba)?sh(?:\s|$)",
    r"\b(?:nc|netcat)\s+-e\b",
]


def load_blocked_patterns() -> list[str]:
    """safety_policy.json 파일로부터 차단할 정규식 패턴 목록을 로드합니다."""
    script_dir = Path(__file__).resolve().parent
    policy_file = script_dir.parent / "safety_policy.json"

    if policy_file.exists():
        try:
            with open(policy_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("blocked_command_patterns", DEFAULT_PATTERNS)
        except Exception:
            pass

    return DEFAULT_PATTERNS


def check_command():
    """인자 또는 stdin으로부터 명령어를 추출하여 보안 정책 위반 여부를 검사합니다."""
    # 1. 커맨드라인 인자로부터 추출
    cmd_to_check = " ".join(sys.argv[1:])

    # 2. 인자가 없고 stdin이 제공된 경우 JSON 파싱 시도 (agy CLI 도구 호출 페이로드)
    if not cmd_to_check.strip() and not sys.stdin.isatty():
        try:
            content = sys.stdin.read()
            if content.strip():
                try:
                    data = json.loads(content)
                    cmd_to_check = data.get("CommandLine") or data.get("command") or content
                except Exception:
                    cmd_to_check = content
        except Exception:
            pass

    blocked_patterns = load_blocked_patterns()

    # 3. 차단 패턴 검사
    for pattern in blocked_patterns:
        if re.search(pattern, cmd_to_check, flags=re.IGNORECASE):
            sys.stderr.write(f"HARNESS_SECURITY_VIOLATION: 보안 정책에 의해 실행이 차단되었습니다: {cmd_to_check}\n")
            sys.stderr.write(f"일치한 보안 규칙 패턴: {pattern}\n")
            # 비정상 종료 코드로 agy CLI에 도구 실행 차단 신호 전달
            sys.exit(1)

    # 4. 정상 통과
    sys.exit(0)


if __name__ == "__main__":
    check_command()
