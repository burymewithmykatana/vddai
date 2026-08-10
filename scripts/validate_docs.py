"""Validate the maintained VDDAI documentation information architecture."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote

import yaml

DOC_DIRECTORIES = {
    "architecture",
    "archive",
    "decisions",
    "engineering",
    "product",
    "reviews",
}
CATALOGED_DIRECTORIES = {
    "architecture",
    "decisions",
    "engineering",
    "product",
}
ALLOWED_ROOT_FILES = {"README.md", "catalog.yaml"}
ALLOWED_AREAS = CATALOGED_DIRECTORIES
ALLOWED_STATUSES = {"accepted", "current", "draft", "superseded"}
MARKDOWN_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
ADR_NAME = re.compile(r"^\d{4}-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
EXTERNAL_SCHEMES = ("http://", "https://", "mailto:")


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _validate_links(markdown_path: Path, root: Path) -> list[str]:
    errors: list[str] = []
    content = markdown_path.read_text(encoding="utf-8")
    resolved_root = root.resolve()

    for match in MARKDOWN_LINK.finditer(content):
        target = match.group(1).strip()
        if not target or target.startswith("#") or target.startswith(EXTERNAL_SCHEMES):
            continue

        target_without_fragment = unquote(target.split("#", 1)[0])
        if not target_without_fragment:
            continue

        if target_without_fragment.startswith("/"):
            resolved = root / target_without_fragment.lstrip("/")
        else:
            resolved = markdown_path.parent / target_without_fragment

        resolved = resolved.resolve()
        try:
            resolved.relative_to(resolved_root)
        except ValueError:
            errors.append(
                f"{_relative(markdown_path, root)} has a link outside the "
                f"repository: {target}"
            )
            continue

        if not resolved.exists():
            errors.append(
                f"{_relative(markdown_path, root)} has a broken link: {target}"
            )

    return errors


def validate_repository(root: Path) -> list[str]:
    """Return documentation-structure errors for one repository root."""
    errors: list[str] = []
    docs_root = root / "docs"
    catalog_path = docs_root / "catalog.yaml"

    if not docs_root.is_dir():
        return ["docs/ directory is missing"]

    actual_root_files = {path.name for path in docs_root.iterdir() if path.is_file()}
    unexpected_root_files = actual_root_files - ALLOWED_ROOT_FILES
    missing_root_files = ALLOWED_ROOT_FILES - actual_root_files
    for name in sorted(unexpected_root_files):
        errors.append(f"unexpected file at docs root: docs/{name}")
    for name in sorted(missing_root_files):
        errors.append(f"required docs root file is missing: docs/{name}")

    actual_directories = {path.name for path in docs_root.iterdir() if path.is_dir()}
    for name in sorted(actual_directories - DOC_DIRECTORIES):
        errors.append(f"unexpected docs category directory: docs/{name}/")
    for name in sorted(DOC_DIRECTORIES - actual_directories):
        errors.append(f"required docs category directory is missing: docs/{name}/")

    markdown_files = sorted(docs_root.rglob("*.md"))
    for path in markdown_files:
        relative = _relative(path, root)
        if path.stat().st_size == 0:
            errors.append(f"empty Markdown document: {relative}")
            continue

        if path.name != "README.md":
            pattern = ADR_NAME if path.parent.name == "decisions" else MARKDOWN_NAME
            if not pattern.fullmatch(path.name):
                errors.append(f"non-kebab-case Markdown filename: {relative}")

        errors.extend(_validate_links(path, root))

    for directory in sorted(DOC_DIRECTORIES):
        index_path = docs_root / directory / "README.md"
        if not index_path.is_file() or index_path.stat().st_size == 0:
            errors.append(
                f"category index is missing or empty: docs/{directory}/README.md"
            )

    if not catalog_path.is_file():
        return errors

    try:
        catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        errors.append(f"docs/catalog.yaml is invalid YAML: {exc}")
        return errors

    if not isinstance(catalog, dict) or catalog.get("schema_version") != 1:
        errors.append("docs/catalog.yaml must declare schema_version: 1")
        return errors

    documents = catalog.get("documents")
    if not isinstance(documents, list):
        errors.append("docs/catalog.yaml documents must be a list")
        return errors

    catalog_paths: set[str] = set()
    for index, entry in enumerate(documents, start=1):
        prefix = f"docs/catalog.yaml documents[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{prefix} must be a mapping")
            continue

        path_value = entry.get("path")
        area = entry.get("area")
        kind = entry.get("kind")
        status = entry.get("status")

        if not isinstance(path_value, str):
            errors.append(f"{prefix}.path must be a string")
            continue
        if path_value in catalog_paths:
            errors.append(f"duplicate catalog path: {path_value}")
        catalog_paths.add(path_value)

        if area not in ALLOWED_AREAS:
            errors.append(f"{prefix}.area is invalid: {area}")
        if not isinstance(kind, str) or not kind:
            errors.append(f"{prefix}.kind must be a non-empty string")
        if status not in ALLOWED_STATUSES:
            errors.append(f"{prefix}.status is invalid: {status}")

        document_path = root / path_value
        if not document_path.is_file():
            errors.append(f"catalog document is missing: {path_value}")
        elif document_path.stat().st_size == 0:
            errors.append(f"catalog document is empty: {path_value}")

        expected_prefix = f"docs/{area}/" if area in ALLOWED_AREAS else None
        if expected_prefix and not path_value.startswith(expected_prefix):
            errors.append(f"catalog path {path_value} does not match area {area}")

    expected_catalog_paths = {
        _relative(path, root)
        for directory in CATALOGED_DIRECTORIES
        for path in (docs_root / directory).glob("*.md")
        if path.name != "README.md"
    }
    for path_value in sorted(expected_catalog_paths - catalog_paths):
        errors.append(f"current document is missing from catalog: {path_value}")
    for path_value in sorted(catalog_paths - expected_catalog_paths):
        errors.append(f"catalog contains a non-current document: {path_value}")

    archive = docs_root / "archive"
    for path in archive.glob("*.md"):
        if path.name == "README.md":
            continue
        first_lines = "\n".join(path.read_text(encoding="utf-8").splitlines()[:12])
        if "Status: Historical" not in first_lines:
            errors.append(
                f"archived document lacks historical status banner: "
                f"{_relative(path, root)}"
            )

    return errors


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root. Defaults to the parent of scripts/.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    errors = validate_repository(root)
    if errors:
        print("Documentation validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    markdown_count = len(list((root / "docs").rglob("*.md")))
    catalog = yaml.safe_load((root / "docs/catalog.yaml").read_text(encoding="utf-8"))
    print(
        "Documentation validation passed: "
        f"{len(catalog['documents'])} canonical documents, "
        f"{markdown_count} Markdown files."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
