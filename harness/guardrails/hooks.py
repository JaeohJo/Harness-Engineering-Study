"""Lifecycle hook manager for Antigravity CLI guardrails and telemetry injection."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Optional

from harness.core.logging import logger
from harness.guardrails.policies import SecurityPolicy


class HookManager:
    """Manages the generation, injection, and cleanup of .agents/hooks.json and guardrail scripts."""

    def __init__(self, policy: Optional[SecurityPolicy] = None):
        self.policy = policy or SecurityPolicy()

    def inject_hooks(self, workspace_dir: str | Path) -> Path:
        """Injects .agents directory containing hooks.json and security interceptor scripts."""
        workspace = Path(workspace_dir).resolve()
        agents_dir = workspace / ".agents"
        scripts_dir = agents_dir / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)

        # 1. Write the Python guardrail script that validates commands
        guardrail_script = scripts_dir / "security_guard.py"
        guardrail_script_content = f"""#!/usr/bin/env python3
import sys
import re
import json

BLOCKED_PATTERNS = {json.dumps(self.policy.blocked_command_patterns)}

def check_stdin_or_args():
    # Attempt to read tool arguments from stdin or arguments
    cmd_to_check = " ".join(sys.argv[1:])
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

    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, cmd_to_check, flags=re.IGNORECASE):
            sys.stderr.write(f"HARNESS_SECURITY_VIOLATION: Command blocked by policy: {{cmd_to_check}}\\n")
            sys.stderr.write(f"Matched rule: {{pattern}}\\n")
            sys.exit(1)

    sys.exit(0)

if __name__ == "__main__":
    check_stdin_or_args()
"""
        guardrail_script.write_text(guardrail_script_content, encoding="utf-8")
        # Make script executable
        guardrail_script.chmod(guardrail_script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        # 2. Write hooks.json
        hooks_config = {
            "harness-safety-guard": {
                "enabled": self.policy.enabled,
                "PreToolUse": [
                    {
                        "matcher": "run_command",
                        "hooks": [
                            {
                                "type": "command",
                                "command": f"./.agents/scripts/security_guard.py",
                                "timeout": self.policy.max_command_timeout,
                            }
                        ],
                    }
                ],
            }
        }

        hooks_file = agents_dir / "hooks.json"
        hooks_file.write_text(json.dumps(hooks_config, indent=2), encoding="utf-8")

        # 3. Write default project guidelines (GEMINI.md)
        gemini_rules = agents_dir / "GEMINI.md"
        if not gemini_rules.exists():
            gemini_rules.write_text(
                "# Harness Engineering Guidelines\n\n"
                "- Do not execute destructive filesystem commands.\n"
                "- Only modify files necessary to solve the assigned task.\n"
                "- Always ensure your code passes syntax and regression checks.\n",
                encoding="utf-8",
            )

        logger.debug(f"Injected harness guardrails and hooks into '{workspace}'")
        return hooks_file
