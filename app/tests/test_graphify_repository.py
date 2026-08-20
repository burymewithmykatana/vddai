from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts import graphify_repository

EXPECTED_VERSION = graphify_repository.EXPECTED_GRAPHIFY_VERSION
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _git(repository: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )


def _create_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "--initial-branch=main")
    _git(repository, "config", "user.email", "graphify-tests@example.invalid")
    _git(repository, "config", "user.name", "Graphify Tests")
    (repository / ".gitignore").write_text("graphify-out/\n", encoding="utf-8")
    (repository / "module.py").write_text(
        "def answer():\n    return 42\n", encoding="utf-8"
    )
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "initial")
    return repository


def _write_graphify_outputs(repository: Path) -> None:
    output_directory = repository / graphify_repository.OUTPUT_DIRECTORY_NAME
    output_directory.mkdir()
    head = graphify_repository.repository_head(repository)
    (output_directory / "graph.json").write_text(
        json.dumps({"built_at_commit": head, "nodes": [], "links": []}),
        encoding="utf-8",
    )
    (output_directory / "graph.html").write_text(
        "<html>graph</html>\n", encoding="utf-8"
    )
    (output_directory / "GRAPH_REPORT.md").write_text(
        "# Graph report\n", encoding="utf-8"
    )
    (output_directory / "repository-callflow.html").write_text(
        "<html>callflow</html>\n", encoding="utf-8"
    )


def _record_state(repository: Path) -> dict[str, object]:
    _write_graphify_outputs(repository)
    return graphify_repository.record_state(
        repository,
        graphify_version=EXPECTED_VERSION,
    )


def _validate(repository: Path) -> dict[str, object]:
    return graphify_repository.validate_state(
        repository,
        graphify_version=EXPECTED_VERSION,
    )


def test_current_state_validates(tmp_path: Path) -> None:
    repository = _create_repository(tmp_path)
    recorded = _record_state(repository)

    validated = _validate(repository)

    assert validated == recorded


def test_dirty_repository_unchanged_since_recording_validates(tmp_path: Path) -> None:
    repository = _create_repository(tmp_path)
    (repository / "module.py").write_text(
        "def answer():\n    return 43\n", encoding="utf-8"
    )
    _record_state(repository)

    assert _validate(repository)["repository_fingerprint"]


def test_tracked_content_drift_is_rejected(tmp_path: Path) -> None:
    repository = _create_repository(tmp_path)
    _record_state(repository)
    (repository / "module.py").write_text(
        "def answer():\n    return 0\n", encoding="utf-8"
    )

    with pytest.raises(graphify_repository.GraphifyIntegrationError, match="stale"):
        _validate(repository)


def test_untracked_content_drift_is_rejected(tmp_path: Path) -> None:
    repository = _create_repository(tmp_path)
    _record_state(repository)
    (repository / "notes.txt").write_text("new untracked input\n", encoding="utf-8")

    with pytest.raises(graphify_repository.GraphifyIntegrationError, match="stale"):
        _validate(repository)


def test_head_commit_drift_is_rejected(tmp_path: Path) -> None:
    repository = _create_repository(tmp_path)
    _record_state(repository)
    (repository / "module.py").write_text(
        "def answer():\n    return 7\n", encoding="utf-8"
    )
    _git(repository, "add", "module.py")
    _git(repository, "commit", "-m", "change answer")

    with pytest.raises(
        graphify_repository.GraphifyIntegrationError, match="head_commit"
    ):
        _validate(repository)


def test_corrupted_graph_checksum_is_rejected(tmp_path: Path) -> None:
    repository = _create_repository(tmp_path)
    _record_state(repository)
    graph_path = repository / "graphify-out" / "graph.json"
    graph_path.write_text(
        graph_path.read_text(encoding="utf-8") + " ", encoding="utf-8"
    )

    with pytest.raises(graphify_repository.GraphifyIntegrationError, match="checksum"):
        _validate(repository)


def test_graphify_version_drift_is_rejected(tmp_path: Path) -> None:
    repository = _create_repository(tmp_path)
    _record_state(repository)

    with pytest.raises(graphify_repository.GraphifyIntegrationError, match="version"):
        graphify_repository.validate_state(
            repository,
            graphify_version="0.9.46",
        )


@pytest.mark.parametrize(
    "failure", ["missing-state", "malformed-state", "missing-output"]
)
def test_missing_or_malformed_state_and_outputs_are_rejected(
    tmp_path: Path,
    failure: str,
) -> None:
    repository = _create_repository(tmp_path)
    _record_state(repository)
    output_directory = repository / "graphify-out"
    state_path = output_directory / graphify_repository.STATE_FILENAME
    if failure == "missing-state":
        state_path.unlink()
    elif failure == "malformed-state":
        state_path.write_text("not-json", encoding="utf-8")
    else:
        (output_directory / "GRAPH_REPORT.md").unlink()

    with pytest.raises(graphify_repository.GraphifyIntegrationError):
        _validate(repository)


def test_query_refuses_to_run_after_validation_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _create_repository(tmp_path)
    command_called = False

    def fail_validation(*args: object, **kwargs: object) -> dict[str, object]:
        raise graphify_repository.GraphifyIntegrationError("stale graph")

    def record_command(*args: object, **kwargs: object) -> object:
        nonlocal command_called
        command_called = True
        raise AssertionError("Graphify must not run")

    monkeypatch.setattr(graphify_repository, "validate_state", fail_validation)
    monkeypatch.setattr(
        graphify_repository,
        "repository_root",
        lambda root: Path(root).resolve(),
    )
    monkeypatch.setattr(graphify_repository, "_run", record_command)

    with pytest.raises(graphify_repository.GraphifyIntegrationError, match="stale"):
        graphify_repository.execute_scoped_query(
            repository,
            ["affected", "answer"],
            graphify_version=EXPECTED_VERSION,
        )

    assert command_called is False


@pytest.mark.parametrize(
    "arguments",
    [
        ["affected", "answer", "--depth", "0"],
        ["affected", "answer", "--depth", "-1"],
        ["query", "answer", "--budget", "0"],
        ["query", "answer", "--budget", "-1"],
    ],
)
def test_non_positive_query_limits_fail_before_graphify_invocation(
    arguments: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    query_called = False

    def record_query(*args: object, **kwargs: object) -> str:
        nonlocal query_called
        query_called = True
        return ""

    monkeypatch.setattr(graphify_repository, "execute_scoped_query", record_query)

    with pytest.raises(SystemExit) as exc_info:
        graphify_repository.main(arguments)

    assert exc_info.value.code == 2
    assert query_called is False
    assert "must be a positive integer" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("arguments", "expected_graphify_arguments"),
    [
        (
            ["affected", "answer", "--depth", "2"],
            ["affected", "answer", "--depth", "2"],
        ),
        (
            ["query", "answer", "--budget", "250"],
            ["query", "answer", "--budget", "250"],
        ),
    ],
)
def test_positive_query_limits_are_forwarded(
    arguments: list[str],
    expected_graphify_arguments: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forwarded_arguments: list[str] | None = None

    def record_query(root: Path, graphify_arguments: list[str]) -> str:
        nonlocal forwarded_arguments
        forwarded_arguments = graphify_arguments
        return ""

    monkeypatch.setattr(graphify_repository, "execute_scoped_query", record_query)

    assert graphify_repository.main(arguments) == 0
    assert forwarded_arguments == expected_graphify_arguments


def test_generated_outputs_are_ignored_and_agent_contract_is_bounded() -> None:
    check_ignore = subprocess.run(
        ["git", "check-ignore", "graphify-out/graph.json"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    agent_contract = (REPOSITORY_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    planner_contract = (
        REPOSITORY_ROOT / ".agents" / "skills" / "vddai-plan" / "SKILL.md"
    ).read_text(encoding="utf-8")
    reviewer_contract = (
        REPOSITORY_ROOT / ".agents" / "skills" / "vddai-review" / "SKILL.md"
    ).read_text(encoding="utf-8")
    qa_contract = (
        REPOSITORY_ROOT / ".agents" / "skills" / "vddai-qa" / "SKILL.md"
    ).read_text(encoding="utf-8")
    documentation_contract = (
        REPOSITORY_ROOT / ".agents" / "skills" / "vddai-documentation" / "SKILL.md"
    ).read_text(encoding="utf-8")
    workflow_contract = (
        REPOSITORY_ROOT / "docs" / "engineering" / "agent-workflow.md"
    ).read_text(encoding="utf-8")
    authority_contract = (
        REPOSITORY_ROOT / "docs" / "engineering" / "repository-intelligence.md"
    ).read_text(encoding="utf-8")

    assert check_ignore.stdout.strip() == "graphify-out/graph.json"
    assert "purpose-specific" in agent_contract
    assert "structural" in agent_contract
    assert "discovery" in agent_contract
    assert "direct repository" in agent_contract
    assert "Graphify-generated agent instructions" in agent_contract
    assert "freshness-validated local Graphify" in planner_contract
    assert "cannot replace review of the exact diff" in reviewer_contract
    assert "cannot prove runtime behavior" in qa_contract
    assert "Never manually edit, curate, catalog, or copy" in documentation_contract
    assert "not a lifecycle stage" in workflow_contract
    assert "rather than a linear hierarchy" in authority_contract
    assert "graphify-out" in (REPOSITORY_ROOT / ".dockerignore").read_text(
        encoding="utf-8"
    )
    assert (
        "graphifyy"
        not in (REPOSITORY_ROOT / "requirements.txt")
        .read_text(encoding="utf-16")
        .lower()
    )
