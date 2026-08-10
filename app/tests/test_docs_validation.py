from pathlib import Path

from scripts.validate_docs import DOC_DIRECTORIES, validate_repository


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_minimal_repository(root: Path) -> None:
    _write(root / "docs/README.md", "# Documentation\n")
    for directory in DOC_DIRECTORIES:
        _write(root / "docs" / directory / "README.md", f"# {directory}\n")

    _write(
        root / "docs/architecture/system.md",
        "# System\n\nSee [docs](../README.md).\n",
    )
    _write(
        root / "docs/archive/snapshot.md",
        "# Snapshot\n\n- Status: Historical\n",
    )
    _write(
        root / "docs/catalog.yaml",
        """schema_version: 1
documents:
  - path: docs/architecture/system.md
    area: architecture
    kind: system-requirements
    status: current
""",
    )


def test_current_repository_documentation_is_valid() -> None:
    repository_root = Path(__file__).resolve().parents[2]

    assert validate_repository(repository_root) == []


def test_validator_accepts_a_minimal_valid_repository(tmp_path: Path) -> None:
    _build_minimal_repository(tmp_path)

    assert validate_repository(tmp_path) == []


def test_validator_rejects_empty_and_uncataloged_documents(tmp_path: Path) -> None:
    _build_minimal_repository(tmp_path)
    _write(tmp_path / "docs/product/empty-document.md", "")

    errors = validate_repository(tmp_path)

    assert "empty Markdown document: docs/product/empty-document.md" in errors
    assert (
        "current document is missing from catalog: " "docs/product/empty-document.md"
    ) in errors


def test_validator_rejects_broken_local_links(tmp_path: Path) -> None:
    _build_minimal_repository(tmp_path)
    _write(
        tmp_path / "docs/architecture/system.md",
        "# System\n\nSee [missing](missing.md).\n",
    )

    errors = validate_repository(tmp_path)

    assert "docs/architecture/system.md has a broken link: missing.md" in errors


def test_validator_rejects_links_outside_repository(tmp_path: Path) -> None:
    _build_minimal_repository(tmp_path)
    _write(
        tmp_path / "docs/architecture/system.md",
        "# System\n\nSee [outside](../../../outside.md).\n",
    )

    errors = validate_repository(tmp_path)

    assert (
        "docs/architecture/system.md has a link outside the repository: "
        "../../../outside.md"
    ) in errors
