"""벤치마크 평가 결과 리포트 생성기 모듈 (Markdown 및 JSON).

배치 실행된 모든 태스크의 통과율(Pass@1), 평균 소요 시간, 텔레메트리 메트릭을 요약하고,
실패한 태스크의 상세 사유 및 Diff를 시각화한 리포트를 자동 생성합니다.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from harness.core.models import EvalResult, EvalStatus, ExecutionResult, TelemetryData


class BenchmarkReport:
    """벤치마크 일괄 실행 결과 집계 및 보고서 생성기."""

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
        """전체 평가 태스크 수."""
        return len(self.eval_results)

    @property
    def passed_tasks(self) -> int:
        """통과(PASS)한 태스크 수."""
        return sum(1 for r in self.eval_results if r.status == EvalStatus.PASS)

    @property
    def failed_tasks(self) -> int:
        """실패(FAIL)한 태스크 수."""
        return sum(1 for r in self.eval_results if r.status == EvalStatus.FAIL)

    @property
    def errored_tasks(self) -> int:
        """에러 또는 타임아웃이 발생한 태스크 수."""
        return sum(1 for r in self.eval_results if r.status in (EvalStatus.ERROR, EvalStatus.TIMEOUT))

    @property
    def pass_rate(self) -> float:
        """최종 성공률(Pass Rate 백분율)."""
        if not self.total_tasks:
            return 0.0
        return (self.passed_tasks / self.total_tasks) * 100.0

    def to_dict(self) -> dict:
        """JSON 저장을 위한 딕셔너리 표현 반환."""
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
        """GitHub Flavored Markdown 형식의 종합 리포트 생성."""
        md = []
        md.append(f"# Antigravity CLI Benchmark Report (벤치마크 평가 리포트)\n")
        md.append(f"- **생성 일시**: `{self.timestamp}`")
        md.append(f"- **대상 모델**: `{self.model_name}`")
        md.append(f"- **최종 해결률 (Pass Rate)**: **{self.pass_rate:.1f}%** ({self.passed_tasks}/{self.total_tasks} 통과)\n")

        # 1. 태스크 요약 테이블
        md.append("## 1. 태스크별 결과 요약\n")
        md.append("| 태스크 ID | 상태 | 소요 시간 | 통과 테스트 | 실패 테스트 | 메시지 |")
        md.append("| :--- | :---: | :---: | :---: | :---: | :--- |")

        for r in self.eval_results:
            if r.status == EvalStatus.PASS:
                status_badge = f"✅ `{r.status.value}`"
            elif r.status == EvalStatus.FAIL:
                status_badge = f"❌ `{r.status.value}`"
            else:
                status_badge = f"⚠️ `{r.status.value}`"

            msg = r.message.replace("\n", " ")[:60]
            md.append(
                f"| `{r.task_id}` | {status_badge} | {r.duration_seconds:.1f}초 | "
                f"{len(r.tests_passed)}건 | {len(r.tests_failed)}건 | {msg} |"
            )

        # 2. 텔레메트리 및 도구 사용 통계
        if self.telemetry_data:
            md.append("\n## 2. 텔레메트리 및 도구 호출 분석\n")
            md.append("| 태스크 ID | 대화 턴 수 | 추론 토큰량 (추정) | 도구 호출 수 | 주요 사용 도구 |")
            md.append("| :--- | :---: | :---: | :---: | :--- |")
            for t in self.telemetry_data:
                top_tools = ", ".join(f"{k}:{v}" for k, v in sorted(t.tool_call_counts.items(), key=lambda x: -x[1])[:3])
                md.append(
                    f"| `{t.task_id}` | {t.total_turns}회 | ~{t.thinking_token_count:,} | {t.total_tool_calls}회 | {top_tools or 'None'} |"
                )

        # 3. 실패 태스크 상세 내역
        failed_evals = [r for r in self.eval_results if r.status != EvalStatus.PASS]
        if failed_evals:
            md.append("\n## 3. 실패 태스크 상세 원인 및 Diff\n")
            for r in failed_evals:
                md.append(f"### 태스크: `{r.task_id}` ({r.status.value})\n")
                md.append(f"**실패 사유**: {r.message}\n")
                if r.diff:
                    md.append("<details><summary>생성된 코드 Diff 보기</summary>\n\n```diff")
                    md.append(r.diff.strip())
                    md.append("```\n</details>\n")

        return "\n".join(md)

    def save(self, output_dir: str | Path) -> tuple[Path, Path]:
        """보고서를 JSON 및 Markdown 파일로 대상 디렉터리에 저장합니다."""
        out = Path(output_dir).resolve()
        out.mkdir(parents=True, exist_ok=True)

        json_path = out / "benchmark_report.json"
        md_path = out / "benchmark_report.md"

        json_path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        md_path.write_text(self.to_markdown(), encoding="utf-8")

        return json_path, md_path
