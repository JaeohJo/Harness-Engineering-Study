"""Unit tests for configuration models and command construction."""

from pathlib import Path
import pytest
from harness.core.config import RunnerConfig, HarnessConfig


def test_runner_config_default_args():
    config = RunnerConfig()
    args = config.build_cli_args(prompt="Fix the bug", workspace_dir="/tmp/test_workspace")

    assert "agy" in args
    assert "--print" in args
    assert "--output-format" in args
    assert "stream-json" in args
    assert "--dangerously-skip-permissions" in args
    assert "--mode" in args
    assert "accept-edits" in args
    assert "--add-dir" in args
    assert "/tmp/test_workspace" in args
    assert args[-1] == "Fix the bug"


def test_runner_config_custom_options():
    config = RunnerConfig(
        model="gemini-1.5-pro",
        effort="high",
        mode="plan",
        sandbox=True,
        timeout_seconds=600.0,
        extra_flags=["--custom-flag", "value"],
    )
    args = config.build_cli_args(prompt="Test prompt", log_file="/tmp/log.txt")

    assert "--model" in args
    assert "gemini-1.5-pro" in args
    assert "--effort" in args
    assert "high" in args
    assert "--mode" in args
    assert "plan" in args
    assert "--sandbox" in args
    assert "--print-timeout" in args
    assert "10m0s" in args
    assert "--log-file" in args
    assert "/tmp/log.txt" in args
    assert "--custom-flag" in args
    assert "value" in args


def test_harness_config_yaml_serialization(tmp_path: Path):
    yaml_file = tmp_path / "config.yaml"
    config = HarnessConfig(
        cleanup_worktree=False,
        concurrency=4,
        runner=RunnerConfig(model="gemini-exp", timeout_seconds=120.0),
    )

    config.to_yaml(yaml_file)
    assert yaml_file.exists()

    loaded = HarnessConfig.from_yaml(yaml_file)
    assert loaded.cleanup_worktree is False
    assert loaded.concurrency == 4
    assert loaded.runner.model == "gemini-exp"
    assert loaded.runner.timeout_seconds == 120.0
