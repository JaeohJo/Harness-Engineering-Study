"""벤치마크 데이터셋 로더 및 관리 모듈.

JSON(배열) 및 JSONL(라인별 레코드) 형식의 평가 태스크 세트를
로딩, 검증 및 저장하는 유틸리티를 제공합니다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator, List, Union
from harness.core.models import TaskSpec


class TaskDataset:
    """평가 대상 엔지니어링 문제(TaskSpec)들의 컬렉션 관리자."""

    def __init__(self, tasks: List[TaskSpec]):
        self.tasks = tasks

    def __len__(self) -> int:
        return len(self.tasks)

    def __iter__(self) -> Iterator[TaskSpec]:
        return iter(self.tasks)

    @classmethod
    def load(cls, path: Union[str, Path]) -> TaskDataset:
        """JSON 또는 JSONL 파일로부터 태스크 데이터셋을 파싱하여 로드합니다."""
        file_path = Path(path).resolve()
        if not file_path.exists():
            raise FileNotFoundError(f"데이터셋 파일을 찾을 수 없습니다: {file_path}")

        tasks: List[TaskSpec] = []
        if file_path.suffix.lower() == ".jsonl":
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if line_str:
                        tasks.append(TaskSpec.model_validate(json.loads(line_str)))
        else:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        tasks.append(TaskSpec.model_validate(item))
                elif isinstance(data, dict):
                    # 단일 태스크 JSON이거나 'tasks' 키를 가진 딕셔너리인 경우 처리
                    if "tasks" in data and isinstance(data["tasks"], list):
                        for item in data["tasks"]:
                            tasks.append(TaskSpec.model_validate(item))
                    else:
                        tasks.append(TaskSpec.model_validate(data))

        return cls(tasks)

    def save(self, path: Union[str, Path]) -> None:
        """태스크 컬렉션을 JSON 또는 JSONL 파일로 디스크에 저장합니다."""
        file_path = Path(path).resolve()
        file_path.parent.mkdir(parents=True, exist_ok=True)

        if file_path.suffix.lower() == ".jsonl":
            with open(file_path, "w", encoding="utf-8") as f:
                for task in self.tasks:
                    f.write(json.dumps(task.model_dump(), ensure_ascii=False) + "\n")
        else:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump([t.model_dump() for t in self.tasks], f, indent=2, ensure_ascii=False)
