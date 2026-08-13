"""SQLite-backed candidate registry with guarded promotion and rollback."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

from pydantic import ValidationError

from app.contracts.model_registry import (
    MODEL_REGISTRY_CODE_VERSION,
    MODEL_REGISTRY_SCHEMA_VERSION,
    ModelCandidate,
    ModelStage,
    PromotionAction,
    PromotionCriteria,
    PromotionOutcome,
    SmokeInferenceEvidence,
)
from app.services.model_package_loader import ProductionModelPackage

DEFAULT_MODEL_REGISTRY_PATH = (
    Path(__file__).resolve().parents[2]
    / "artifacts"
    / "registry"
    / "model_registry.sqlite3"
)

PackageValidator = Callable[[ModelCandidate], ProductionModelPackage]
SmokeInference = Callable[[ProductionModelPackage], SmokeInferenceEvidence]


class ModelRegistryError(RuntimeError):
    """Base error for registry contract failures."""


class PromotionRejectedError(ModelRegistryError):
    """A promotion or rollback failed closed and remains audited."""

    def __init__(self, attempt_id: str, reasons: list[str]) -> None:
        self.attempt_id = attempt_id
        self.reasons = tuple(reasons)
        super().__init__(
            f"Registry transition {attempt_id} was rejected: " + "; ".join(reasons)
        )


def _utc_timestamp(value: datetime | None = None) -> str:
    timestamp = value or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise ModelRegistryError("Registry timestamps must include timezone.")
    return timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _required_text(value: str, *, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ModelRegistryError(f"{field} must be non-empty.")
    return normalized


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as artifact_file:
            for chunk in iter(lambda: artifact_file.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ModelRegistryError(
            "Candidate package manifest is missing or unreadable."
        ) from exc
    return f"sha256:{digest.hexdigest()}"


class ModelRegistry:
    """Local registry whose state transitions are explicit and auditable."""

    def __init__(self, database_path: Path, *, repository_root: Path) -> None:
        self.database_path = database_path.resolve()
        self.repository_root = repository_root.resolve()
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
                CREATE TABLE IF NOT EXISTS registry_metadata (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    schema_version TEXT NOT NULL,
                    code_version TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS model_candidates (
                    model_version TEXT PRIMARY KEY,
                    package_id TEXT NOT NULL UNIQUE,
                    metadata_json TEXT NOT NULL,
                    registered_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS registry_environments (
                    environment TEXT PRIMARY KEY
                        CHECK (environment IN ('staging', 'production')),
                    active_version TEXT,
                    rollback_version TEXT,
                    updated_at TEXT,
                    updated_by TEXT,
                    reason TEXT,
                    FOREIGN KEY (active_version) REFERENCES model_candidates(model_version)
                        ON DELETE RESTRICT,
                    FOREIGN KEY (rollback_version) REFERENCES model_candidates(model_version)
                        ON DELETE RESTRICT
                );

                CREATE TABLE IF NOT EXISTS promotion_attempts (
                    attempt_id TEXT PRIMARY KEY,
                    action TEXT NOT NULL CHECK (action IN ('promote', 'rollback')),
                    environment TEXT NOT NULL
                        CHECK (environment IN ('staging', 'production')),
                    requested_version TEXT NOT NULL,
                    previous_version TEXT,
                    outcome TEXT NOT NULL
                        CHECK (outcome IN ('pending', 'approved', 'rejected')),
                    requested_by TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    requested_at TEXT NOT NULL,
                    decided_at TEXT,
                    criteria_json TEXT NOT NULL,
                    checks_json TEXT,
                    rejection_reasons_json TEXT,
                    FOREIGN KEY (requested_version)
                        REFERENCES model_candidates(model_version) ON DELETE RESTRICT,
                    FOREIGN KEY (previous_version)
                        REFERENCES model_candidates(model_version) ON DELETE RESTRICT
                );

                CREATE INDEX IF NOT EXISTS ix_model_candidates_registered_at
                    ON model_candidates(registered_at);
                CREATE INDEX IF NOT EXISTS ix_promotion_attempts_environment_time
                    ON promotion_attempts(environment, requested_at);
                """)
            metadata = connection.execute(
                "SELECT schema_version FROM registry_metadata WHERE singleton = 1"
            ).fetchone()
            if metadata is None:
                connection.execute(
                    "INSERT INTO registry_metadata "
                    "(singleton, schema_version, code_version) VALUES (1, ?, ?)",
                    (MODEL_REGISTRY_SCHEMA_VERSION, MODEL_REGISTRY_CODE_VERSION),
                )
            elif metadata["schema_version"] != MODEL_REGISTRY_SCHEMA_VERSION:
                raise ModelRegistryError("Unsupported model-registry schema version.")
            for environment in (ModelStage.STAGING.value, ModelStage.PRODUCTION.value):
                connection.execute(
                    "INSERT OR IGNORE INTO registry_environments (environment) VALUES (?)",
                    (environment,),
                )

    def register_candidate(self, candidate: ModelCandidate) -> None:
        manifest_path = (
            self.repository_root / candidate.package_manifest_path
        ).resolve()
        try:
            manifest_path.relative_to(self.repository_root)
        except ValueError as exc:
            raise ModelRegistryError(
                "Candidate manifest escapes repository root."
            ) from exc
        if _sha256_file(manifest_path) != candidate.package_manifest_sha256:
            raise ModelRegistryError(
                "Candidate package-manifest checksum does not match."
            )
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO model_candidates "
                    "(model_version, package_id, metadata_json, registered_at) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        candidate.model_version,
                        candidate.package_id,
                        candidate.model_dump_json(),
                        _utc_timestamp(candidate.registered_at),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ModelRegistryError(
                "Model version and package ID are immutable and already registered."
            ) from exc

    def get_candidate(self, model_version: str) -> ModelCandidate:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT metadata_json FROM model_candidates WHERE model_version = ?",
                (_required_text(model_version, field="Model version"),),
            ).fetchone()
        if row is None:
            raise ModelRegistryError(f"Model version {model_version!r} was not found.")
        try:
            return ModelCandidate.model_validate_json(row["metadata_json"])
        except ValidationError as exc:
            raise ModelRegistryError("Stored candidate metadata is invalid.") from exc

    def get_environment(self, environment: ModelStage) -> dict[str, object]:
        self._require_environment(environment)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM registry_environments WHERE environment = ?",
                (environment.value,),
            ).fetchone()
        if row is None:  # pragma: no cover - protected by schema initialization
            raise ModelRegistryError("Registry environment state is missing.")
        return dict(row)

    def get_stage(self, model_version: str) -> ModelStage:
        self.get_candidate(model_version)
        production = self.get_environment(ModelStage.PRODUCTION)
        staging = self.get_environment(ModelStage.STAGING)
        if production["active_version"] == model_version:
            return ModelStage.PRODUCTION
        if staging["active_version"] == model_version:
            return ModelStage.STAGING
        return ModelStage.CANDIDATE

    def promote(
        self,
        model_version: str,
        *,
        environment: ModelStage,
        requested_by: str,
        reason: str,
        criteria: PromotionCriteria,
        package_validator: PackageValidator,
        smoke_inference: SmokeInference,
    ) -> str:
        self._require_environment(environment)
        return self._transition(
            action=PromotionAction.PROMOTE,
            model_version=model_version,
            environment=environment,
            requested_by=requested_by,
            reason=reason,
            criteria=criteria,
            package_validator=package_validator,
            smoke_inference=smoke_inference,
        )

    def rollback(
        self,
        *,
        environment: ModelStage,
        requested_by: str,
        reason: str,
        criteria: PromotionCriteria,
        package_validator: PackageValidator,
        smoke_inference: SmokeInference,
    ) -> str:
        self._require_environment(environment)
        state = self.get_environment(environment)
        rollback_version = state["rollback_version"]
        if not isinstance(rollback_version, str):
            raise ModelRegistryError(
                f"Environment {environment.value!r} has no explicit rollback target."
            )
        return self._transition(
            action=PromotionAction.ROLLBACK,
            model_version=rollback_version,
            environment=environment,
            requested_by=requested_by,
            reason=reason,
            criteria=criteria,
            package_validator=package_validator,
            smoke_inference=smoke_inference,
        )

    def _transition(
        self,
        *,
        action: PromotionAction,
        model_version: str,
        environment: ModelStage,
        requested_by: str,
        reason: str,
        criteria: PromotionCriteria,
        package_validator: PackageValidator,
        smoke_inference: SmokeInference,
    ) -> str:
        candidate = self.get_candidate(model_version)
        state = self.get_environment(environment)
        previous_version = state["active_version"]
        attempt_id = str(uuid4())
        actor = _required_text(requested_by, field="Requested by")
        transition_reason = _required_text(reason, field="Promotion reason")
        requested_at = _utc_timestamp()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO promotion_attempts (
                    attempt_id, action, environment, requested_version,
                    previous_version, outcome, requested_by, reason,
                    requested_at, criteria_json
                ) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)
                """,
                (
                    attempt_id,
                    action.value,
                    environment.value,
                    model_version,
                    previous_version,
                    actor,
                    transition_reason,
                    requested_at,
                    criteria.model_dump_json(),
                ),
            )

        reasons: list[str] = []
        checks: dict[str, object] = {
            "metrics": candidate.metrics.values,
            "package_validation": "not_run",
            "smoke_inference": "not_run",
        }
        if action is PromotionAction.PROMOTE and previous_version == model_version:
            reasons.append(
                "Requested model is already active in the target environment."
            )
        if action is PromotionAction.PROMOTE and environment is ModelStage.PRODUCTION:
            staging = self.get_environment(ModelStage.STAGING)
            if staging["active_version"] != model_version:
                reasons.append(
                    "Production promotion requires the exact version to be active in staging."
                )
        for metric_name, minimum in criteria.minimum_metrics.items():
            observed = candidate.metrics.values.get(metric_name)
            if observed is None:
                reasons.append(f"Required metric {metric_name!r} is missing.")
            elif observed < minimum:
                reasons.append(
                    f"Metric {metric_name!r}={observed} is below required minimum {minimum}."
                )

        package: ProductionModelPackage | None = None
        try:
            package = package_validator(candidate)
            self._validate_loaded_package(candidate, package)
            checks["package_validation"] = "passed"
        except Exception as exc:  # fail closed while retaining safe evidence
            checks["package_validation"] = "failed"
            reasons.append(f"Package compatibility check failed: {type(exc).__name__}.")

        if package is not None:
            try:
                smoke = smoke_inference(package)
                if smoke.package_id != package.package_id:
                    raise ModelRegistryError(
                        "Smoke result identifies a different package."
                    )
                checks["smoke_inference"] = smoke.model_dump(mode="json")
            except Exception as exc:  # fail closed while retaining safe evidence
                checks["smoke_inference"] = "failed"
                reasons.append(f"Smoke inference failed: {type(exc).__name__}.")

        if reasons:
            self._reject(attempt_id, reasons=reasons, checks=checks)
            raise PromotionRejectedError(attempt_id, reasons)

        decided_at = _utc_timestamp()
        concurrent_rejection: list[str] | None = None
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT active_version FROM registry_environments WHERE environment = ?",
                (environment.value,),
            ).fetchone()
            if current is None or current["active_version"] != previous_version:
                concurrent_rejection = ["Environment state changed during validation."]
                connection.execute(
                    """
                    UPDATE promotion_attempts
                    SET outcome = 'rejected', decided_at = ?, checks_json = ?,
                        rejection_reasons_json = ?
                    WHERE attempt_id = ? AND outcome = 'pending'
                    """,
                    (
                        decided_at,
                        _canonical_json(checks),
                        _canonical_json(concurrent_rejection),
                        attempt_id,
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE registry_environments
                    SET active_version = ?, rollback_version = ?, updated_at = ?,
                        updated_by = ?, reason = ?
                    WHERE environment = ?
                    """,
                    (
                        model_version,
                        previous_version,
                        decided_at,
                        actor,
                        transition_reason,
                        environment.value,
                    ),
                )
                connection.execute(
                    """
                    UPDATE promotion_attempts
                    SET outcome = 'approved', decided_at = ?, checks_json = ?,
                        rejection_reasons_json = '[]'
                    WHERE attempt_id = ? AND outcome = 'pending'
                    """,
                    (decided_at, _canonical_json(checks), attempt_id),
                )
        if concurrent_rejection is not None:
            raise PromotionRejectedError(attempt_id, concurrent_rejection)
        return attempt_id

    @staticmethod
    def _validate_loaded_package(
        candidate: ModelCandidate,
        package: ProductionModelPackage,
    ) -> None:
        lineage = package.lineage
        mismatches = (
            package.package_id != candidate.package_id,
            lineage.dataset_name != candidate.dataset_name,
            lineage.dataset_category != candidate.dataset_category,
            lineage.dataset_version != candidate.dataset_version,
            lineage.manifest_fingerprint != candidate.manifest_fingerprint,
            lineage.feature_bank_sha256 != candidate.feature_bank_sha256,
        )
        if any(mismatches):
            raise ModelRegistryError(
                "Loaded package lineage does not match its candidate record."
            )

    def _reject(
        self,
        attempt_id: str,
        *,
        reasons: list[str],
        checks: dict[str, object],
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE promotion_attempts
                SET outcome = 'rejected', decided_at = ?, checks_json = ?,
                    rejection_reasons_json = ?
                WHERE attempt_id = ? AND outcome = 'pending'
                """,
                (
                    _utc_timestamp(),
                    _canonical_json(checks),
                    _canonical_json(reasons),
                    attempt_id,
                ),
            )

    def get_attempt(self, attempt_id: str) -> dict[str, object]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM promotion_attempts WHERE attempt_id = ?",
                (_required_text(attempt_id, field="Attempt ID"),),
            ).fetchone()
        if row is None:
            raise ModelRegistryError(f"Promotion attempt {attempt_id!r} was not found.")
        result = dict(row)
        result["criteria"] = json.loads(result.pop("criteria_json"))
        checks_json = result.pop("checks_json")
        rejection_json = result.pop("rejection_reasons_json")
        result["checks"] = json.loads(checks_json) if checks_json else None
        result["rejection_reasons"] = (
            json.loads(rejection_json) if rejection_json else None
        )
        return result

    @staticmethod
    def _require_environment(environment: ModelStage) -> None:
        if environment not in (ModelStage.STAGING, ModelStage.PRODUCTION):
            raise ModelRegistryError(
                "Candidates are registered, not promoted to candidate."
            )
