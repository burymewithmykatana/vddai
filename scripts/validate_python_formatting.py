"""Run Black only on Python files added or changed in an explicit Git range."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

import black

ZERO_SHA = "0" * 40


class FormattingValidationError(RuntimeError):
    """Raised when the Git comparison used for formatting cannot be trusted."""


def _run_git(
    repository_root: Path,
    arguments: Sequence[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["git", "-c", f"safe.directory={repository_root.as_posix()}", *arguments],
            cwd=repository_root,
            check=check,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = ""
        if isinstance(exc, subprocess.CalledProcessError):
            detail = exc.stderr.decode("utf-8", errors="replace").strip()
        message = f"Git formatting-range inspection failed: {' '.join(arguments)}"
        if detail:
            message += f": {detail}"
        raise FormattingValidationError(message) from exc


def _decode_paths(output: bytes) -> set[str]:
    paths: set[str] = set()
    for value in output.split(b"\0"):
        if not value:
            continue
        path = value.decode("utf-8")
        if Path(path).suffix.casefold() == ".py":
            paths.add(Path(path).as_posix())
    return paths


def _validate_commit(repository_root: Path, revision: str, *, label: str) -> None:
    if not revision.strip():
        raise FormattingValidationError(f"{label} revision must not be empty.")
    _run_git(
        repository_root,
        ["rev-parse", "--verify", f"{revision}^{{commit}}"],
    )


def changed_python_files(
    repository_root: Path,
    *,
    base: str | None,
    head: str,
) -> tuple[Path, ...]:
    """Resolve added, copied, modified, or renamed Python files to check."""
    root = repository_root.resolve()
    _validate_commit(root, head, label="head")

    if base is not None:
        normalized_base = base.strip()
        if normalized_base and normalized_base != ZERO_SHA:
            _validate_commit(root, normalized_base, label="base")
            result = _run_git(
                root,
                [
                    "diff",
                    "--name-only",
                    "--diff-filter=ACMR",
                    "-z",
                    normalized_base,
                    head,
                    "--",
                    "*.py",
                ],
            )
            relative_paths = _decode_paths(result.stdout)
        else:
            result = _run_git(
                root,
                [
                    "diff-tree",
                    "--root",
                    "--no-commit-id",
                    "--name-only",
                    "--diff-filter=ACMR",
                    "-r",
                    "-z",
                    head,
                    "--",
                    "*.py",
                ],
            )
            relative_paths = _decode_paths(result.stdout)
    else:
        tracked = _run_git(
            root,
            [
                "diff",
                "--name-only",
                "--diff-filter=ACMR",
                "-z",
                head,
                "--",
                "*.py",
            ],
        )
        untracked = _run_git(
            root,
            ["ls-files", "--others", "--exclude-standard", "-z", "--", "*.py"],
        )
        relative_paths = _decode_paths(tracked.stdout) | _decode_paths(untracked.stdout)

    resolved: list[Path] = []
    for relative_path in sorted(relative_paths):
        candidate = (root / relative_path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise FormattingValidationError(
                f"Changed Python path escapes the repository: {relative_path}"
            ) from exc
        if candidate.is_file():
            resolved.append(candidate)
    return tuple(resolved)


def run_black(paths: Sequence[Path]) -> int:
    """Run the pinned Black module over the selected paths."""
    failures: list[str] = []
    mode = black.Mode()
    for path in paths:
        try:
            would_change = black.format_file_in_place(
                path,
                fast=False,
                mode=mode,
                write_back=black.WriteBack.CHECK,
            )
        except Exception as exc:
            failures.append(f"{path}: {exc}")
            continue
        if would_change:
            failures.append(f"would reformat {path}")

    for failure in failures:
        print(failure, file=sys.stderr)
    return 1 if failures else 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root. Defaults to the parent of scripts/.",
    )
    parser.add_argument(
        "--base",
        default=os.environ.get("VDDAI_FORMAT_BASE_SHA"),
        help=(
            "Base commit for CI. Omit locally to check staged, unstaged, and "
            "untracked Python files. An all-zero SHA checks a root commit."
        ),
    )
    parser.add_argument(
        "--head",
        default=os.environ.get("VDDAI_FORMAT_HEAD_SHA", "HEAD"),
        help="Head commit or local comparison anchor. Defaults to HEAD.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        paths = changed_python_files(args.root, base=args.base, head=args.head)
    except FormattingValidationError as exc:
        print(f"Formatting validation failed: {exc}", file=sys.stderr)
        return 1

    if not paths:
        print("Formatting validation passed: no added or changed Python files.")
        return 0

    relative_paths = [
        path.relative_to(args.root.resolve()).as_posix() for path in paths
    ]
    print("Checking changed Python files with Black:")
    for path in relative_paths:
        print(f"- {path}")
    return run_black(paths)


if __name__ == "__main__":
    raise SystemExit(main())
