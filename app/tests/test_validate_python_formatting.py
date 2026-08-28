import subprocess
from pathlib import Path

from scripts.validate_python_formatting import (
    ZERO_SHA,
    changed_python_files,
    run_black,
)


def _git(repository: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=True,
        capture_output=True,
    )


def _commit(repository: Path, message: str) -> str:
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", message)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repository(tmp_path: Path) -> tuple[Path, str]:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "ci-tests@example.com")
    _git(tmp_path, "config", "user.name", "CI Tests")
    (tmp_path / "existing.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("initial\n", encoding="utf-8")
    return tmp_path, _commit(tmp_path, "initial")


def test_changed_python_files_selects_only_live_python_changes(tmp_path: Path) -> None:
    repository, base = _repository(tmp_path)
    (repository / "existing.py").write_text("VALUE = 2\n", encoding="utf-8")
    (repository / "new.py").write_text("NEW_VALUE = 3\n", encoding="utf-8")
    (repository / "notes.md").write_text("changed\n", encoding="utf-8")
    head = _commit(repository, "changes")

    paths = changed_python_files(repository, base=base, head=head)

    assert {path.name for path in paths} == {"existing.py", "new.py"}


def test_changed_python_files_checks_all_python_files_in_root_commit(
    tmp_path: Path,
) -> None:
    repository, head = _repository(tmp_path)

    paths = changed_python_files(repository, base=ZERO_SHA, head=head)

    assert [path.name for path in paths] == ["existing.py"]


def test_local_formatting_selection_includes_untracked_python(
    tmp_path: Path,
) -> None:
    repository, head = _repository(tmp_path)
    (repository / "existing.py").write_text("VALUE = 2\n", encoding="utf-8")
    (repository / "untracked.py").write_text("VALUE = 3\n", encoding="utf-8")

    paths = changed_python_files(repository, base=None, head=head)

    assert {path.name for path in paths} == {"existing.py", "untracked.py"}


def test_black_rejects_new_formatting_debt(tmp_path: Path) -> None:
    clean = tmp_path / "clean.py"
    unformatted = tmp_path / "unformatted.py"
    clean.write_text("VALUE = 1\n", encoding="utf-8")
    unformatted.write_text("VALUES=[1,2,3]\n", encoding="utf-8")

    assert run_black([clean]) == 0
    assert run_black([unformatted]) != 0
