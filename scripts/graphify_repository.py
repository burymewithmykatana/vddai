"""Build and query a freshness-validated local Graphify repository graph."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

EXPECTED_GRAPHIFY_VERSION = "0.9.47"
STATE_SCHEMA_VERSION = 1
OUTPUT_DIRECTORY_NAME = "graphify-out"
STATE_FILENAME = "vddai-graph-state.json"
GRAPH_FILENAME = "graph.json"
REQUIRED_STATIC_OUTPUTS = (GRAPH_FILENAME, "graph.html", "GRAPH_REPORT.md")
FINGERPRINT_DOMAIN = b"vddai-repository-fingerprint-v1\0"


class GraphifyIntegrationError(RuntimeError):
    """Raised when Graphify evidence is unavailable, invalid, or stale."""


def _run(
    command: Sequence[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    text: bool = True,
) -> subprocess.CompletedProcess[Any]:
    try:
        return subprocess.run(
            list(command),
            cwd=cwd,
            env=env,
            check=True,
            capture_output=True,
            text=text,
            encoding="utf-8" if text else None,
            errors="replace" if text else None,
        )
    except FileNotFoundError as exc:
        raise GraphifyIntegrationError(f"Command is unavailable: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if isinstance(exc.stderr, str) else ""
        detail = f": {stderr}" if stderr else ""
        raise GraphifyIntegrationError(
            f"Command failed ({' '.join(command)}){detail}"
        ) from exc


def repository_root(root: Path | str) -> Path:
    candidate = Path(root).resolve()
    result = _run(["git", "rev-parse", "--show-toplevel"], cwd=candidate)
    discovered = Path(result.stdout.strip()).resolve()
    if discovered != candidate:
        raise GraphifyIntegrationError(
            f"Expected repository root {candidate}, but Git resolved {discovered}."
        )
    return candidate


def repository_head(root: Path | str) -> str:
    resolved_root = repository_root(root)
    result = _run(["git", "rev-parse", "HEAD"], cwd=resolved_root)
    return result.stdout.strip()


def _git_bytes(root: Path, *arguments: str) -> bytes:
    result = _run(["git", *arguments], cwd=root, text=False)
    return bytes(result.stdout)


def repository_fingerprint(root: Path | str) -> str:
    """Hash HEAD, index/worktree state, and tracked/nonignored file contents."""

    resolved_root = repository_root(root)
    digest = hashlib.sha256()
    digest.update(FINGERPRINT_DOMAIN)
    head = repository_head(resolved_root).encode("ascii")
    digest.update(b"head\0" + head + b"\0")

    status = _git_bytes(
        resolved_root,
        "status",
        "--porcelain=v2",
        "-z",
        "--untracked-files=all",
    )
    digest.update(b"status\0" + status + b"\0")

    listed = _git_bytes(
        resolved_root,
        "ls-files",
        "-z",
        "--cached",
        "--others",
        "--exclude-standard",
    )
    for relative_bytes in sorted(path for path in listed.split(b"\0") if path):
        relative_path = os.fsdecode(relative_bytes)
        file_path = resolved_root / relative_path
        digest.update(b"path\0" + relative_bytes + b"\0")
        try:
            file_stat = file_path.lstat()
        except FileNotFoundError:
            digest.update(b"missing\0")
            continue

        if stat.S_ISLNK(file_stat.st_mode):
            digest.update(b"symlink\0")
            digest.update(os.fsencode(os.readlink(file_path)) + b"\0")
            continue
        if not stat.S_ISREG(file_stat.st_mode):
            digest.update(f"unsupported:{file_stat.st_mode}\0".encode("ascii"))
            continue

        digest.update(f"file:{file_stat.st_mode & 0o111:o}\0".encode("ascii"))
        with file_path.open("rb") as file_handle:
            for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")

    return digest.hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def installed_graphify_version(root: Path | str) -> str:
    resolved_root = repository_root(root)
    if shutil.which("graphify") is None:
        raise GraphifyIntegrationError(
            "Graphify is not installed. Use the isolated installation documented in "
            "docs/engineering/repository-intelligence.md."
        )
    environment = os.environ.copy()
    environment["GRAPHIFY_QUERY_LOG_DISABLE"] = "1"
    result = _run(["graphify", "--version"], cwd=resolved_root, env=environment)
    match = re.search(r"(?<!\d)(\d+\.\d+\.\d+)(?!\d)", result.stdout)
    if match is None:
        raise GraphifyIntegrationError(
            f"Could not parse Graphify version from: {result.stdout.strip()!r}."
        )
    version = match.group(1)
    if version != EXPECTED_GRAPHIFY_VERSION:
        raise GraphifyIntegrationError(
            f"Graphify {EXPECTED_GRAPHIFY_VERSION} is required; found {version}."
        )
    return version


def _output_directory(root: Path) -> Path:
    return root / OUTPUT_DIRECTORY_NAME


def _state_path(root: Path) -> Path:
    return _output_directory(root) / STATE_FILENAME


def _required_outputs(root: Path) -> list[Path]:
    output_directory = _output_directory(root)
    outputs = [output_directory / name for name in REQUIRED_STATIC_OUTPUTS]
    callflows = sorted(output_directory.glob("*-callflow.html"))
    if len(callflows) != 1:
        raise GraphifyIntegrationError(
            "Expected exactly one Graphify *-callflow.html output; "
            f"found {len(callflows)}."
        )
    return [*outputs, callflows[0]]


def _validate_nonempty_outputs(root: Path) -> list[Path]:
    outputs = _required_outputs(root)
    for output in outputs:
        if not output.is_file() or output.stat().st_size == 0:
            raise GraphifyIntegrationError(
                f"Required Graphify output is missing or empty: {output}"
            )
    return outputs


def _read_graph_built_at_commit(graph_path: Path) -> str:
    try:
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GraphifyIntegrationError(
            f"Malformed Graphify graph: {graph_path}"
        ) from exc
    built_at_commit = graph.get("built_at_commit")
    if not isinstance(built_at_commit, str) or not built_at_commit:
        raise GraphifyIntegrationError(
            "Graphify graph.json does not contain a valid built_at_commit."
        )
    return built_at_commit


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_name = temporary_file.name
            json.dump(payload, temporary_file, indent=2, sort_keys=True)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_name, path)
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def record_state(
    root: Path | str,
    *,
    graphify_version: str | None = None,
    fingerprint: str | None = None,
) -> dict[str, Any]:
    resolved_root = repository_root(root)
    version = graphify_version or installed_graphify_version(resolved_root)
    if version != EXPECTED_GRAPHIFY_VERSION:
        raise GraphifyIntegrationError(
            f"Graphify {EXPECTED_GRAPHIFY_VERSION} is required; found {version}."
        )
    outputs = _validate_nonempty_outputs(resolved_root)
    head = repository_head(resolved_root)
    graph_path = _output_directory(resolved_root) / GRAPH_FILENAME
    if _read_graph_built_at_commit(graph_path) != head:
        raise GraphifyIntegrationError(
            "Graphify graph.json built_at_commit does not match repository HEAD."
        )
    payload: dict[str, Any] = {
        "schema_version": STATE_SCHEMA_VERSION,
        "repository_root": str(resolved_root),
        "head_commit": head,
        "repository_fingerprint": fingerprint or repository_fingerprint(resolved_root),
        "graph_sha256": file_sha256(graph_path),
        "built_at_commit": head,
        "graphify_version": version,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "extraction_mode": "code-only",
        "outputs": [
            str(path.relative_to(resolved_root).as_posix()) for path in outputs
        ],
    }
    _atomic_write_json(_state_path(resolved_root), payload)
    return payload


def _load_state(root: Path) -> dict[str, Any]:
    state_path = _state_path(root)
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GraphifyIntegrationError(
            "Graphify state is missing. Build the graph or inspect repository sources directly."
        ) from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GraphifyIntegrationError(
            "Graphify state is malformed. Rebuild it or inspect repository sources directly."
        ) from exc
    if not isinstance(state, dict):
        raise GraphifyIntegrationError("Graphify state must be a JSON object.")
    return state


def validate_state(
    root: Path | str,
    *,
    graphify_version: str | None = None,
) -> dict[str, Any]:
    resolved_root = repository_root(root)
    state = _load_state(resolved_root)
    version = graphify_version or installed_graphify_version(resolved_root)
    required_values = {
        "schema_version": STATE_SCHEMA_VERSION,
        "repository_root": str(resolved_root),
        "head_commit": repository_head(resolved_root),
        "graphify_version": EXPECTED_GRAPHIFY_VERSION,
        "extraction_mode": "code-only",
    }
    for field, expected in required_values.items():
        if state.get(field) != expected:
            raise GraphifyIntegrationError(
                f"Graphify state is stale or incompatible: {field} does not match."
            )
    if version != EXPECTED_GRAPHIFY_VERSION or state.get("graphify_version") != version:
        raise GraphifyIntegrationError(
            "Installed Graphify version does not match the pinned graph state."
        )
    current_fingerprint = repository_fingerprint(resolved_root)
    if state.get("repository_fingerprint") != current_fingerprint:
        raise GraphifyIntegrationError(
            "Graphify state is stale: repository contents changed after the build."
        )

    outputs = _validate_nonempty_outputs(resolved_root)
    expected_output_names = [
        str(path.relative_to(resolved_root).as_posix()) for path in outputs
    ]
    if state.get("outputs") != expected_output_names:
        raise GraphifyIntegrationError(
            "Graphify state output inventory does not match."
        )
    graph_path = _output_directory(resolved_root) / GRAPH_FILENAME
    if state.get("graph_sha256") != file_sha256(graph_path):
        raise GraphifyIntegrationError(
            "Graphify graph.json checksum does not match state."
        )
    graph_commit = _read_graph_built_at_commit(graph_path)
    if graph_commit != state.get("built_at_commit") or graph_commit != state.get(
        "head_commit"
    ):
        raise GraphifyIntegrationError(
            "Graphify graph and state built_at_commit values do not match."
        )
    generated_at = state.get("generated_at_utc")
    if not isinstance(generated_at, str) or not generated_at:
        raise GraphifyIntegrationError("Graphify state has no generation timestamp.")
    return state


def _graphify_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["GRAPHIFY_QUERY_LOG_DISABLE"] = "1"
    return environment


def build_graph(root: Path | str) -> dict[str, Any]:
    resolved_root = repository_root(root)
    version = installed_graphify_version(resolved_root)
    fingerprint_before = repository_fingerprint(resolved_root)
    output_directory = _output_directory(resolved_root)
    output_directory.mkdir(parents=True, exist_ok=True)

    # Without a matching sidecar, prior generated outputs are never accepted as fresh.
    _state_path(resolved_root).unlink(missing_ok=True)
    environment = _graphify_environment()
    _run(
        ["graphify", "extract", ".", "--code-only"],
        cwd=resolved_root,
        env=environment,
    )
    _run(
        ["graphify", "cluster-only", ".", "--no-label"],
        cwd=resolved_root,
        env=environment,
    )
    _run(
        ["graphify", "export", "callflow-html"],
        cwd=resolved_root,
        env=environment,
    )
    _validate_nonempty_outputs(resolved_root)
    fingerprint_after = repository_fingerprint(resolved_root)
    if fingerprint_after != fingerprint_before:
        raise GraphifyIntegrationError(
            "Repository contents changed while Graphify was building; no fresh state was recorded."
        )
    state = record_state(
        resolved_root,
        graphify_version=version,
        fingerprint=fingerprint_after,
    )
    validate_state(resolved_root, graphify_version=version)
    return state


def execute_scoped_query(
    root: Path | str,
    graphify_arguments: Sequence[str],
    *,
    graphify_version: str | None = None,
) -> str:
    resolved_root = repository_root(root)
    validate_state(resolved_root, graphify_version=graphify_version)
    result = _run(
        [
            "graphify",
            *graphify_arguments,
            "--graph",
            str(_output_directory(resolved_root) / GRAPH_FILENAME),
        ],
        cwd=resolved_root,
        env=_graphify_environment(),
    )
    return result.stdout


def _positive_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Use freshness-validated local Graphify repository evidence."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("build", help="Build code-only Graphify outputs and state.")
    subparsers.add_parser("validate", help="Validate that Graphify evidence is fresh.")

    affected = subparsers.add_parser("affected", help="Find affected graph nodes.")
    affected.add_argument("target")
    affected.add_argument("--depth", type=_positive_integer, default=3)

    query = subparsers.add_parser("query", help="Run a natural-language graph query.")
    query.add_argument("question")
    query.add_argument("--dfs", action="store_true")
    query.add_argument("--budget", type=_positive_integer)

    path = subparsers.add_parser("path", help="Find a path between two graph nodes.")
    path.add_argument("source")
    path.add_argument("target")

    explain = subparsers.add_parser("explain", help="Explain a graph node.")
    explain.add_argument("node")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    arguments = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    try:
        if arguments.command == "build":
            state = build_graph(root)
            print(
                "Graphify repository evidence built and validated at "
                f"{state['head_commit']}."
            )
            return 0
        if arguments.command == "validate":
            state = validate_state(root)
            print(
                "Graphify repository evidence is fresh at " f"{state['head_commit']}."
            )
            return 0

        graphify_arguments: list[str]
        if arguments.command == "affected":
            graphify_arguments = [
                "affected",
                arguments.target,
                "--depth",
                str(arguments.depth),
            ]
        elif arguments.command == "query":
            graphify_arguments = ["query", arguments.question]
            if arguments.dfs:
                graphify_arguments.append("--dfs")
            if arguments.budget is not None:
                graphify_arguments.extend(["--budget", str(arguments.budget)])
        elif arguments.command == "path":
            graphify_arguments = ["path", arguments.source, arguments.target]
        else:
            graphify_arguments = ["explain", arguments.node]
        print(execute_scoped_query(root, graphify_arguments), end="")
        return 0
    except GraphifyIntegrationError as exc:
        print(
            f"Graphify repository evidence is unavailable: {exc} "
            "Fall back to direct repository inspection.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
