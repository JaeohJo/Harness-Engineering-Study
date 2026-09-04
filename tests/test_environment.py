"""Unit tests for GitWorktreeEnvironment and LocalTempEnvironment."""

import subprocess
from pathlib import Path
import pytest

from harness.environment.worktree import GitWorktreeEnvironment
from harness.environment.temp_dir import LocalTempEnvironment


@pytest.fixture
def sample_git_repo(tmp_path: Path) -> Path:
    """Initializes a temporary git repository with an initial commit."""
    repo_dir = tmp_path / "sample_repo"
    repo_dir.mkdir()

    subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo_dir), check=True)

    test_file = repo_dir / "calculator.py"
    test_file.write_text("def add(a, b):\n    return a - b\n")

    subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=str(repo_dir), check=True)

    return repo_dir


def test_git_worktree_lifecycle(sample_git_repo: Path):
    env = GitWorktreeEnvironment(
        repo_path=sample_git_repo,
        base_commit="HEAD",
        task_id="calc_fix",
        auto_cleanup=True,
    )

    with env:
        worktree_path = env.path
        assert worktree_path.exists()
        calc_file = worktree_path / "calculator.py"
        assert calc_file.exists()

        # Modify file to fix the bug
        calc_file.write_text("def add(a, b):\n    return a + b\n")

        # Create a new file
        new_file = worktree_path / "utils.py"
        new_file.write_text("def identity(x):\n    return x\n")

        modified_files = env.get_modified_files()
        assert "calculator.py" in modified_files
        assert "utils.py" in modified_files

        diff = env.get_diff()
        assert "+    return a + b" in diff
        assert "-    return a - b" in diff
        assert "def identity(x):" in diff

    # After exit from context manager, cleanup should have happened
    assert not worktree_path.exists()


def test_local_temp_environment(tmp_path: Path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "app.py").write_text("print('hello')\n")

    env = LocalTempEnvironment(source_dir=source, task_id="test_local")
    with env:
        app_file = env.path / "app.py"
        assert app_file.exists()

        app_file.write_text("print('hello world')\n")
        (env.path / "extra.txt").write_text("extra\n")

        modified = env.get_modified_files()
        assert "app.py" in modified
        assert "extra.txt" in modified

        diff = env.get_diff()
        assert "-print('hello')" in diff
        assert "+print('hello world')" in diff

    assert not env._temp_dir
