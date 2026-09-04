"""Configuration models and loader for the Antigravity Harness system."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
import yaml
from pydantic import BaseModel, Field


class RunnerConfig(BaseModel):
    """Configuration options for executing the Antigravity CLI (agy)."""
    model: Optional[str] = Field(default=None, description="Model for the CLI session")
    effort: Optional[Literal["low", "medium", "high"]] = Field(
        default=None, description="Reasoning effort level"
    )
    mode: Optional[Literal["accept-edits", "plan"]] = Field(
        default="accept-edits", description="Agent execution mode"
    )
    dangerously_skip_permissions: bool = Field(
        default=True,
        description="Auto-approve all tool permission requests without prompting (essential for headless automation)",
    )
    sandbox: bool = Field(
        default=False,
        description="Run in a sandbox with terminal restrictions enabled",
    )
    timeout_seconds: float = Field(
        default=300.0, description="Execution timeout for agy print mode in seconds"
    )
    agy_bin_path: str = Field(
        default="agy", description="Path or command name for the Antigravity CLI binary"
    )
    extra_flags: List[str] = Field(
        default_factory=list, description="Additional custom CLI flags"
    )

    def build_cli_args(
        self,
        prompt: Optional[str] = None,
        workspace_dir: Optional[str] = None,
        log_file: Optional[str] = None,
    ) -> List[str]:
        """Constructs the command-line argument list for invoking agy headlessly."""
        args = [self.agy_bin_path]

        # Use print mode for non-interactive execution
        args.append("--print")
        args.extend(["--output-format", "stream-json"])

        if self.dangerously_skip_permissions:
            args.append("--dangerously-skip-permissions")

        if self.sandbox:
            args.append("--sandbox")

        if self.model:
            args.extend(["--model", self.model])

        if self.effort:
            args.extend(["--effort", self.effort])

        if self.mode:
            args.extend(["--mode", self.mode])

        if self.timeout_seconds:
            timeout_m = int(self.timeout_seconds // 60)
            timeout_s = int(self.timeout_seconds % 60)
            args.extend(["--print-timeout", f"{timeout_m}m{timeout_s}s"])

        if log_file:
            args.extend(["--log-file", str(log_file)])

        if workspace_dir:
            args.extend(["--add-dir", str(workspace_dir)])

        # Append any extra user flags
        args.extend(self.extra_flags)

        if prompt:
            args.append(prompt)

        return args


class HarnessConfig(BaseModel):
    """Global configuration for running evaluation benchmarks and managing tasks."""
    output_dir: Path = Field(
        default_factory=lambda: Path("reports"),
        description="Directory where benchmark results, diffs, and transcripts will be saved",
    )
    runner: RunnerConfig = Field(
        default_factory=RunnerConfig, description="CLI runner configuration"
    )
    cleanup_worktree: bool = Field(
        default=True, description="Whether to automatically delete isolated git worktrees after completion"
    )
    enable_guardrails: bool = Field(
        default=True, description="Whether to inject safety hooks.json into task workspaces"
    )
    concurrency: int = Field(
        default=1, description="Maximum number of parallel task executions"
    )

    @classmethod
    def from_yaml(cls, path: str | Path) -> HarnessConfig:
        """Load configuration from a YAML file."""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        return cls.model_validate(data)

    def to_yaml(self, path: str | Path) -> None:
        """Save configuration to a YAML file."""
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            yaml.dump(self.model_dump(mode="json"), f, default_flow_style=False, sort_keys=False)
