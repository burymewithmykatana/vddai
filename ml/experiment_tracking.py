"""Immutable, queryable experiment-run persistence for the offline ML pipeline."""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from string import hexdigits
from typing import Iterable, Mapping
from uuid import uuid4

EXPERIMENT_TRACKER_SCHEMA_VERSION = "vddai.experiment_tracker.v1"
EXPERIMENT_TRACKER_CODE_VERSION = "vddai.experiment_tracker.sqlite.v1"
DEFAULT_EXPERIMENT_TRACKER_PATH = (
    Path(__file__).resolve().parents[1]
    / "artifacts"
    / "experiments"
    / "experiments.sqlite3"
)
RUN_STATUSES = ("running", "completed", "failed")


class ExperimentTrackingError(RuntimeError):
    """Raised when an experiment record would violate the tracker contract."""


@dataclass(frozen=True)
class TrackedArtifact:
    """One immutable artifact reference stored for an experiment run."""

    name: str
    path: str
    sha256: str
    schema_version: str | None = None
    code_version: str | None = None


def _utc_timestamp(value: datetime | None = None) -> str:
    timestamp = value or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise ExperimentTrackingError("Experiment timestamps must include timezone.")
    return timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _required_text(value: str, *, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ExperimentTrackingError(f"{field} must be non-empty.")
    return normalized


def _canonical_json(value: object, *, field: str) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ExperimentTrackingError(f"{field} must be finite JSON data.") from exc


def _canonical_sha256(value: str, *, field: str) -> str:
    normalized = _required_text(value, field=field)
    digest = normalized.removeprefix("sha256:")
    if (
        not normalized.startswith("sha256:")
        or len(digest) != 64
        or digest != digest.lower()
        or any(character not in hexdigits for character in digest)
    ):
        raise ExperimentTrackingError(f"{field} must be canonical SHA-256.")
    return normalized


def _commit_revision(value: str) -> str:
    normalized = _required_text(value, field="Code revision")
    if (
        len(normalized) != 40
        or normalized != normalized.lower()
        or any(character not in hexdigits for character in normalized)
    ):
        raise ExperimentTrackingError("Code revision must be a full Git commit SHA.")
    return normalized


def _validate_artifact(artifact: TrackedArtifact) -> TrackedArtifact:
    name = _required_text(artifact.name, field="Artifact name")
    path = _required_text(artifact.path, field="Artifact path")
    portable_path = PurePosixPath(path)
    if (
        portable_path.is_absolute()
        or PureWindowsPath(path).is_absolute()
        or ".." in portable_path.parts
        or ".." in PureWindowsPath(path).parts
    ):
        raise ExperimentTrackingError(
            "Artifact paths must be repository-relative and non-traversing."
        )
    sha256 = _canonical_sha256(artifact.sha256, field="Artifact checksum")
    return TrackedArtifact(
        name=name,
        path=portable_path.as_posix(),
        sha256=sha256,
        schema_version=artifact.schema_version,
        code_version=artifact.code_version,
    )


class ExperimentTracker:
    """SQLite-backed experiment ledger with immutable terminal records."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path.resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS tracker_metadata (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    schema_version TEXT NOT NULL,
                    code_version TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS experiment_runs (
                    run_id TEXT PRIMARY KEY,
                    experiment_name TEXT NOT NULL,
                    status TEXT NOT NULL
                        CHECK (status IN ('running', 'completed', 'failed')),
                    dataset_name TEXT NOT NULL,
                    dataset_category TEXT NOT NULL,
                    dataset_version TEXT NOT NULL,
                    manifest_fingerprint TEXT NOT NULL,
                    code_revision TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    failure_reason TEXT
                );

                CREATE TABLE IF NOT EXISTS experiment_parameters (
                    run_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, name),
                    FOREIGN KEY (run_id) REFERENCES experiment_runs(run_id)
                        ON DELETE RESTRICT
                );

                CREATE TABLE IF NOT EXISTS experiment_metrics (
                    run_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    value REAL NOT NULL,
                    PRIMARY KEY (run_id, name),
                    FOREIGN KEY (run_id) REFERENCES experiment_runs(run_id)
                        ON DELETE RESTRICT
                );

                CREATE TABLE IF NOT EXISTS experiment_artifacts (
                    run_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    path TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    schema_version TEXT,
                    code_version TEXT,
                    PRIMARY KEY (run_id, name),
                    FOREIGN KEY (run_id) REFERENCES experiment_runs(run_id)
                        ON DELETE RESTRICT
                );

                CREATE INDEX IF NOT EXISTS ix_experiment_runs_status
                    ON experiment_runs(status);
                CREATE INDEX IF NOT EXISTS ix_experiment_runs_dataset_version
                    ON experiment_runs(dataset_version);
                CREATE INDEX IF NOT EXISTS ix_experiment_metrics_name_value
                    ON experiment_metrics(name, value);
                """)
            metadata = connection.execute(
                "SELECT schema_version, code_version FROM tracker_metadata "
                "WHERE singleton = 1"
            ).fetchone()
            if metadata is None:
                connection.execute(
                    "INSERT INTO tracker_metadata "
                    "(singleton, schema_version, code_version) VALUES (1, ?, ?)",
                    (
                        EXPERIMENT_TRACKER_SCHEMA_VERSION,
                        EXPERIMENT_TRACKER_CODE_VERSION,
                    ),
                )
            elif metadata["schema_version"] != EXPERIMENT_TRACKER_SCHEMA_VERSION:
                raise ExperimentTrackingError(
                    "Unsupported experiment-tracker schema version."
                )

    def start_run(
        self,
        *,
        experiment_name: str,
        dataset_name: str,
        dataset_category: str,
        dataset_version: str,
        manifest_fingerprint: str,
        code_revision: str,
        parameters: Mapping[str, object],
        run_id: str | None = None,
        started_at: datetime | None = None,
    ) -> str:
        resolved_run_id = _required_text(
            run_id or str(uuid4()),
            field="Run ID",
        )
        parameter_rows = [
            (
                resolved_run_id,
                _required_text(name, field="Parameter name"),
                _canonical_json(value, field=f"Parameter {name}"),
            )
            for name, value in parameters.items()
        ]
        if len({row[1] for row in parameter_rows}) != len(parameter_rows):
            raise ExperimentTrackingError("Experiment parameter names must be unique.")

        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO experiment_runs (
                        run_id, experiment_name, status, dataset_name,
                        dataset_category, dataset_version, manifest_fingerprint,
                        code_revision, started_at
                    ) VALUES (?, ?, 'running', ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        resolved_run_id,
                        _required_text(experiment_name, field="Experiment name"),
                        _required_text(dataset_name, field="Dataset name"),
                        _required_text(dataset_category, field="Dataset category"),
                        _required_text(dataset_version, field="Dataset version"),
                        _canonical_sha256(
                            manifest_fingerprint,
                            field="Manifest fingerprint",
                        ),
                        _commit_revision(code_revision),
                        _utc_timestamp(started_at),
                    ),
                )
                connection.executemany(
                    "INSERT INTO experiment_parameters "
                    "(run_id, name, value_json) VALUES (?, ?, ?)",
                    parameter_rows,
                )
        except sqlite3.IntegrityError as exc:
            raise ExperimentTrackingError(
                f"Experiment run {resolved_run_id!r} already exists or is invalid."
            ) from exc
        return resolved_run_id

    def complete_run(
        self,
        run_id: str,
        *,
        metrics: Mapping[str, float | int],
        artifacts: Iterable[TrackedArtifact],
        completed_at: datetime | None = None,
    ) -> None:
        resolved_run_id = _required_text(run_id, field="Run ID")
        metric_rows: list[tuple[str, str, float]] = []
        for name, value in metrics.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ExperimentTrackingError("Experiment metrics must be numeric.")
            numeric_value = float(value)
            if not math.isfinite(numeric_value):
                raise ExperimentTrackingError("Experiment metrics must be finite.")
            metric_rows.append(
                (
                    resolved_run_id,
                    _required_text(name, field="Metric name"),
                    numeric_value,
                )
            )
        artifact_rows = [
            (
                resolved_run_id,
                validated.name,
                validated.path,
                validated.sha256,
                validated.schema_version,
                validated.code_version,
            )
            for validated in (_validate_artifact(item) for item in artifacts)
        ]
        if len({row[1] for row in metric_rows}) != len(metric_rows):
            raise ExperimentTrackingError("Experiment metric names must be unique.")
        if len({row[1] for row in artifact_rows}) != len(artifact_rows):
            raise ExperimentTrackingError("Experiment artifact names must be unique.")

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_running(connection, resolved_run_id)
            connection.executemany(
                "INSERT INTO experiment_metrics "
                "(run_id, name, value) VALUES (?, ?, ?)",
                metric_rows,
            )
            connection.executemany(
                """
                INSERT INTO experiment_artifacts (
                    run_id, name, path, sha256, schema_version, code_version
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                artifact_rows,
            )
            connection.execute(
                """
                UPDATE experiment_runs
                SET status = 'completed', completed_at = ?, failure_reason = NULL
                WHERE run_id = ?
                """,
                (_utc_timestamp(completed_at), resolved_run_id),
            )

    def fail_run(
        self,
        run_id: str,
        *,
        failure_reason: str,
        completed_at: datetime | None = None,
    ) -> None:
        resolved_run_id = _required_text(run_id, field="Run ID")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_running(connection, resolved_run_id)
            connection.execute(
                """
                UPDATE experiment_runs
                SET status = 'failed', completed_at = ?, failure_reason = ?
                WHERE run_id = ?
                """,
                (
                    _utc_timestamp(completed_at),
                    _required_text(failure_reason, field="Failure reason"),
                    resolved_run_id,
                ),
            )

    @staticmethod
    def _require_running(connection: sqlite3.Connection, run_id: str) -> None:
        row = connection.execute(
            "SELECT status FROM experiment_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            raise ExperimentTrackingError(f"Experiment run {run_id!r} was not found.")
        if row["status"] != "running":
            raise ExperimentTrackingError(
                f"Experiment run {run_id!r} is already terminal."
            )

    def get_run(self, run_id: str) -> dict[str, object]:
        resolved_run_id = _required_text(run_id, field="Run ID")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM experiment_runs WHERE run_id = ?",
                (resolved_run_id,),
            ).fetchone()
            if row is None:
                raise ExperimentTrackingError(
                    f"Experiment run {resolved_run_id!r} was not found."
                )
            parameters = {
                item["name"]: json.loads(item["value_json"])
                for item in connection.execute(
                    "SELECT name, value_json FROM experiment_parameters "
                    "WHERE run_id = ? ORDER BY name",
                    (resolved_run_id,),
                )
            }
            metrics = {
                item["name"]: item["value"]
                for item in connection.execute(
                    "SELECT name, value FROM experiment_metrics "
                    "WHERE run_id = ? ORDER BY name",
                    (resolved_run_id,),
                )
            }
            artifacts = [
                dict(item)
                for item in connection.execute(
                    """
                    SELECT name, path, sha256, schema_version, code_version
                    FROM experiment_artifacts
                    WHERE run_id = ? ORDER BY name
                    """,
                    (resolved_run_id,),
                )
            ]
        result = dict(row)
        result["parameters"] = parameters
        result["metrics"] = metrics
        result["artifacts"] = artifacts
        result["tracker_schema_version"] = EXPERIMENT_TRACKER_SCHEMA_VERSION
        result["tracker_code_version"] = EXPERIMENT_TRACKER_CODE_VERSION
        return result

    def list_runs(
        self,
        *,
        status: str | None = None,
        experiment_name: str | None = None,
        dataset_version: str | None = None,
    ) -> list[dict[str, object]]:
        if status is not None and status not in RUN_STATUSES:
            raise ExperimentTrackingError("Unsupported experiment status filter.")
        conditions: list[str] = []
        values: list[str] = []
        for column, value in (
            ("status", status),
            ("experiment_name", experiment_name),
            ("dataset_version", dataset_version),
        ):
            if value is not None:
                conditions.append(f"{column} = ?")
                values.append(value)
        where_clause = ""
        if conditions:
            where_clause = " WHERE " + " AND ".join(conditions)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT run_id FROM experiment_runs"
                + where_clause
                + " ORDER BY started_at DESC, run_id DESC",
                values,
            ).fetchall()
        return [self.get_run(row["run_id"]) for row in rows]
