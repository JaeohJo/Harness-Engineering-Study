"""Security policies and rule specifications for agent guardrails."""

from __future__ import annotations

import re
from typing import List
from pydantic import BaseModel, Field


DEFAULT_BLOCKED_COMMAND_PATTERNS = [
    r"\brm\s+[^;\|]*-[a-zA-Z0-9_-]*r[a-zA-Z0-9_-]*[^;\|]*/(?:\s|$)",    # rm -rf / or rm -r -f / or rm --recursive /
    r"\brm\s+[^;\|]*-[a-zA-Z0-9_-]*r[a-zA-Z0-9_-]*[^;\|]*\.\./(?:\s|$)", # rm -rf ../
    r"\brm\s+[^;\|]*-[a-zA-Z0-9_-]*r[a-zA-Z0-9_-]*[^;\|]*\.git(?:\s|$|/)", # rm -rf .git
    r"\bmkfs\b",                                                         # Prevent filesystem formatting
    r"\bdd\s+if=.*of=/dev/",                                             # Prevent raw block device writing
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:",                        # Fork bomb
    r"\bchmod\s+-R\s+777\s+/(?:\s|$)",                                  # Global permission destruction
    r"\bcurl\s+.*\|\s*(?:ba)?sh(?:\s|$)",                               # Pipe to shell from internet
    r"\bwget\s+.*\|\s*(?:ba)?sh(?:\s|$)",
    r"\b(?:nc|netcat)\s+-e\b",                                          # Reverse shells
]


class SecurityPolicy(BaseModel):
    """Configuration for safety checks and tool execution constraints."""
    enabled: bool = True
    blocked_command_patterns: List[str] = Field(
        default_factory=lambda: list(DEFAULT_BLOCKED_COMMAND_PATTERNS),
        description="Regex patterns for shell commands that must be blocked immediately",
    )
    allow_git_write: bool = False
    max_command_timeout: int = 60

    def check_command(self, command_line: str) -> tuple[bool, str]:
        """Validates whether a command is safe to execute.

        Returns (is_safe, reason).
        """
        if not self.enabled:
            return True, "Policy checks disabled"

        for pattern in self.blocked_command_patterns:
            if re.search(pattern, command_line, flags=re.IGNORECASE):
                return False, f"Command matches blocked security pattern: '{pattern}'"

        return True, "Command passed security checks"
