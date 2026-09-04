"""Benchmark and evaluation reporting generator (Markdown & JSON)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from harness.core.models import EvalResult, EvalStatus, ExecutionResult, TelemetryData


class BenchmarkReport:
    """Aggregated report data for a batch of task evaluations."""

    def __init__(
        self,
        eval_results: List[EvalResult],
        exec_results: Optional[List[ExecutionResult]] = None,
        telemetry_data: Optional[List[TelemetryData]] = None,
        model_name: Optional[str] = None,
    ):
        self.eval_results = eval_results
        self.exec_results = exec_results or []
        self.telemetry_data = telemetry_data or []
        self.model_name = model_name or "unknown_model"
        self.timestamp = datetime.now().isoformat()

    @property
    def total_tasks(self) -> int:
        return len(self.eval_results)

    @property
    def passed_tasks(self) -> int:
        return sum(1 for r in self.eval_results if r.status == EvalStatus.PASS)

    @property
    def failed_tasks(self) -> int:
        return sum(1 for r in self.eval_results if r.status == EvalStatus.FAIL)

    @property
    def errored_tasks(self) -> int:
        return sum(1 for r in self.eval_results if r.status in (EvalStatus.ERROR, EvalStatus.TIMEOUT))

    @property
    def pass_rate(self) -> float:
        if not self.total_tasks:
            return 0.0
        return (self.passed_tasks / self.total_tasks) * 100.0

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "model": self.model_name,
            "total_tasks": self.total_tasks,
            "passed_tasks": self.passed_tasks,
            "failed_tasks": self.failed_tasks,
            "errored_tasks": self.errored_tasks,
            "pass_rate_percent": round(self.pass_rate, 2),
            "eval_results": [r.model_dump() for r in self.eval_results],
            "telemetry": [t.model_dump() for t in self.telemetry_data],
        }

    def to_markdown(self) -> str:
        md = []
        md.append(f"# Antigravity CLI Benchmark Report\n")
        md.append(f"- **Generated At**: `{self.timestamp}`")
        md.append(f"- **Target Model**: `{self.model_name}`")
        md.append(f"- **Pass Rate**: **{self.pass_rate:.1f}%** ({self.passed_tasks}/{self.total_tasks} passed)\n")

        # Overview Table
        md.append("## Task Summary\n")
        md.append("| Task ID | Status | Duration | Tests Passed | Tests Failed | Message |")
        md.append("| :--- | :---: | :---: | :---: | :---: | :--- |")

        for r in self.eval_results:
            status_badge = f"**{r.status.value}**"
            if r.status == EvalStatus.PASS:
                status_badge = f"✅ `{r.status.value}`"
            elif r.status == EvalStatus.FAIL:
                status_badge = f"❌ `{r.status.value}`"
            else:
                status_badge = f"⚠️ `{r.status.value}`"

            msg = r.message.replace("\n", " ")[:60]
            md.append(
                f"| `{r.task_id}` | {status_badge} | {r.duration_seconds:.1f}s | "
                f"{len(r.tests_passed)} | {len(r.tests_failed)} | {msg} |"
            )

        # Telemetry Section
        if self.telemetry_data:
            md.append("\n## Telemetry & Tool Usage\n")
            md.append("| Task ID | Turns | Thinking Tokens | Tool Calls | Top Tools |")
            md.append("| :--- | :---: | :---: | :---: | :--- |")
            for t in self.telemetry_data:
                top_tools = ", ".join(f"{k}:{v}" for k, v in sorted(t.tool_call_counts.items(), key=lambda x: -x[1])[:3])
                md.append(
                    f"| `{t.task_id}` | {t.total_turns} | ~{t.thinking_token_count:,} | {t.total_tool_calls} | {top_tools or 'None'} |"
                )

        # Detailed Task Failures
        failed_evals = [r for r in self.eval_results if r.status != EvalStatus.PASS]
        if failed_evals:
            md.append("\n## Failure Details\n")
            for r in failed_evals:
                md.append(f"### Task: `{r.task_id}` ({r.status.value})\n")
                md.append(f"**Message**: {r.message}\n")
                if r.diff:
                    md.append("<details><summary>Generated Diff</summary>\n\n```diff")
                    md.append(r.diff.strip())
                    md.append("```\n</details>\n")

        return "\n".join(md)

    def save(self, output_dir: str | Path) -> tuple[Path, Path]:
        """Saves report as JSON and Markdown files in the target directory."""
        out = Path(output_dir).resolve()
        out.mkdir(parents=True, exist_ok=True)

        json_path = out / "benchmark_report.json"
        md_path = out / "benchmark_report.md"

        json_path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        md_path.write_text(self.to_markdown(), encoding="utf-8")

        return json_path, md_path
