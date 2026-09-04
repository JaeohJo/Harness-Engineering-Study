"""Antigravity CLI 생명주기 훅(Lifecycle Hooks) 주입 및 관리자 모듈.

Antigravity의 .agents/hooks.json 표준 규격에 따라 PreToolUse, PostToolUse 등의
이벤트를 가로채어 보안 가드레일 및 지침(GEMINI.md)을 대상 워크스페이스에 자동 주입합니다.
"""

from __future__ import annotations

import json
import shutil
import stat
from pathlib import Path
from typing import Optional

from harness.core.logging import logger
from harness.guardrails.policies import SecurityPolicy

# 템플릿 디렉터리 경로
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


class HookManager:
    """워크스페이스 내 .agents/hooks.json 및 보안 인터셉터 스크립트 생성을 담당하는 관리자."""

    def __init__(self, policy: Optional[SecurityPolicy] = None):
        self.policy = policy or SecurityPolicy()

    def inject_hooks(self, workspace_dir: str | Path) -> Path:
        """대상 워크스페이스에 .agents 디렉터리와 hooks.json, 보안 가드레일 스크립트를 주입합니다.

        주입 구성요소:
        1. .agents/safety_policy.json: 차단할 명령어 패턴 및 정책 설정 파일
        2. .agents/scripts/security_guard.py: 명령어 실행 전 인자를 가로채어 검사하는 인터셉터 (PreToolUse)
        3. .agents/hooks.json: agy CLI가 인식하는 훅 이벤트 매핑 설정 파일
        4. .agents/GEMINI.md: 에이전트의 컨텍스트에 자동 주입되는 엔지니어링 가이드라인 규칙
        """
        workspace = Path(workspace_dir).resolve()
        agents_dir = workspace / ".agents"
        scripts_dir = agents_dir / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)

        # 1. 보안 정책 JSON 파일 작성 (.agents/safety_policy.json)
        policy_file = agents_dir / "safety_policy.json"
        policy_file.write_text(
            json.dumps(self.policy.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # 2. 독립된 템플릿 파일로부터 보안 가드레일 스크립트 복사 및 실행 권한 부여
        guardrail_script = scripts_dir / "security_guard.py"
        template_guard_script = TEMPLATE_DIR / "security_guard.py"

        if template_guard_script.exists():
            shutil.copy2(template_guard_script, guardrail_script)
        else:
            raise FileNotFoundError(f"보안 가드 템플릿 스크립트를 찾을 수 없습니다: {template_guard_script}")

        # 실행 권한(chmod +x) 부여
        guardrail_script.chmod(guardrail_script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        # 3. agy CLI 공식 규격의 hooks.json 생성
        hooks_config = {
            "harness-safety-guard": {
                "enabled": self.policy.enabled,
                "PreToolUse": [
                    {
                        "matcher": "run_command",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "./.agents/scripts/security_guard.py",
                                "timeout": self.policy.max_command_timeout,
                            }
                        ],
                    }
                ],
            }
        }

        hooks_file = agents_dir / "hooks.json"
        hooks_file.write_text(json.dumps(hooks_config, indent=2, ensure_ascii=False), encoding="utf-8")

        # 4. 에이전트 프롬프트 컨텍스트에 자동 주입되는 GEMINI.md 규칙 생성
        gemini_rules = agents_dir / "GEMINI.md"
        if not gemini_rules.exists():
            gemini_rules.write_text(
                "# 하네스 엔지니어링 실행 가이드라인\n\n"
                "- 파괴적인 파일시스템 및 루트 디렉터리 삭제 명령어를 절대 실행하지 마십시오.\n"
                "- 주어진 태스크를 해결하는 데 필수적인 파일만 정확히 수정하십시오.\n"
                "- 모든 코드 변경 후 구문 에러가 없는지, 테스트가 정상 통과하는지 검증하십시오.\n",
                encoding="utf-8",
            )

        logger.debug(f"워크스페이스 가드레일 주입 완료: '{workspace}'")
        return hooks_file
