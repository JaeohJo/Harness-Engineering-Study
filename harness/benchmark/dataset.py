"""Dataset loader and task specification management."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator, List, Union
from harness.core.models import TaskSpec


class TaskDataset:
    """Manages collections of task specifications for benchmarking."""

    def __init__(self, tasks: List[TaskSpec]):
        self.tasks = tasks

    def __len__(self) -> int:
        return len(self.tasks)

    def __iter__(self) -> Iterator[TaskSpec]:
        return iter(self.tasks)

    @classmethod
    def load(cls, path: Union[str, Path]) -> TaskDataset:
        """Loads tasks from a JSON (array) or JSONL (line-by-line) file."""
        file_path = Path(path).resolve()
        if not file_path.exists():
            raise FileNotFoundError(f"Dataset file does not exist: {file_path}")

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
                    # Single task JSON or dict with 'tasks' key
                    if "tasks" in data and isinstance(data["tasks"], list):
                        for item in data["tasks"]:
                            tasks.append(TaskSpec.model_validate(item))
                    else:
                        tasks.append(TaskSpec.model_validate(data))

        return cls(tasks)

    def save(self, path: Union[str, Path]) -> None:
        """Saves tasks to JSON or JSONL format."""
        file_path = Path(path).resolve()
        file_path.parent.mkdir(parents=True, exist_ok=True)

        if file_path.suffix.lower() == ".jsonl":
            with open(file_path, "w", encoding="utf-8") as f:
                for task in self.tasks:
                    f.write(json.dumps(task.model_dump()) + "\n")
        else:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump([t.model_dump() for t in self.tasks], f, indent=2)
