"""Read-only resolution of the one explicitly promoted production candidate."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app.contracts.model_registry import (
    MODEL_REGISTRY_SCHEMA_VERSION,
    ModelCandidate,
    ModelStage,
)
from app.services.model_package_loader import ProductionModelPackage


class PromotedModelResolutionError(RuntimeError):
    """Production registry state cannot safely select one model package."""


@dataclass(frozen=True, slots=True)
class PromotedModelSelection:
    """Immutable internal selection used as the runtime cache key."""

    model_version: str
    package_id: str
    package_manifest_path: Path
    package_manifest_sha256: str
    feature_bank_dir: Path
    feature_bank_sha256: str
    dataset_name: str
    dataset_category: str
    dataset_version: str
    manifest_fingerprint: str

    @classmethod
    def from_candidate(
        cls,
        candidate: ModelCandidate,
        *,
        repository_root: Path,
    ) -> PromotedModelSelection:
        resolved_root = repository_root.resolve()
        manifest_path = (resolved_root / candidate.package_manifest_path).resolve()
        feature_bank_dir = (resolved_root / candidate.feature_bank_dir).resolve()
        for path, name in (
            (manifest_path, "Package manifest"),
            (feature_bank_dir, "Feature-bank directory"),
        ):
            try:
                path.relative_to(resolved_root)
            except ValueError as exc:
                raise PromotedModelResolutionError(
                    f"{name} escapes the configured artifact root."
                ) from exc
        if not manifest_path.is_file():
            raise PromotedModelResolutionError(
                "Promoted package manifest is missing or unreadable."
            )
        if not feature_bank_dir.is_dir():
            raise PromotedModelResolutionError(
                "Promoted feature-bank directory is missing or unreadable."
            )
        if _sha256_file(manifest_path) != candidate.package_manifest_sha256:
            raise PromotedModelResolutionError(
                "Promoted package-manifest checksum does not match the registry."
            )
        return cls(
            model_version=candidate.model_version,
            package_id=candidate.package_id,
            package_manifest_path=manifest_path,
            package_manifest_sha256=candidate.package_manifest_sha256,
            feature_bank_dir=feature_bank_dir,
            feature_bank_sha256=candidate.feature_bank_sha256,
            dataset_name=candidate.dataset_name,
            dataset_category=candidate.dataset_category,
            dataset_version=candidate.dataset_version,
            manifest_fingerprint=candidate.manifest_fingerprint,
        )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as artifact_file:
            for chunk in iter(lambda: artifact_file.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise PromotedModelResolutionError(
            "Promoted package manifest is missing or unreadable."
        ) from exc
    return f"sha256:{digest.hexdigest()}"


class PromotedModelResolver:
    """Resolve production state without creating or mutating registry data."""

    def __init__(self, registry_path: Path, *, repository_root: Path) -> None:
        self.registry_path = registry_path.resolve()
        self.repository_root = repository_root.resolve()

    def resolve(self) -> PromotedModelSelection:
        if not self.registry_path.is_file():
            raise PromotedModelResolutionError(
                "Model registry is missing or unreadable."
            )
        try:
            connection = sqlite3.connect(
                f"{self.registry_path.as_uri()}?mode=ro",
                uri=True,
            )
            connection.row_factory = sqlite3.Row
            with connection:
                metadata = connection.execute(
                    "SELECT schema_version FROM registry_metadata WHERE singleton = 1"
                ).fetchone()
                state = connection.execute(
                    "SELECT active_version FROM registry_environments "
                    "WHERE environment = ?",
                    (ModelStage.PRODUCTION.value,),
                ).fetchone()
                if metadata is None or metadata["schema_version"] != (
                    MODEL_REGISTRY_SCHEMA_VERSION
                ):
                    raise PromotedModelResolutionError(
                        "Model registry schema is missing or incompatible."
                    )
                if state is None or not state["active_version"]:
                    raise PromotedModelResolutionError(
                        "No production model version is promoted."
                    )
                candidate_row = connection.execute(
                    "SELECT metadata_json FROM model_candidates "
                    "WHERE model_version = ?",
                    (state["active_version"],),
                ).fetchone()
        except PromotedModelResolutionError:
            raise
        except sqlite3.Error as exc:
            raise PromotedModelResolutionError(
                "Model registry is unreadable or incompatible."
            ) from exc
        finally:
            if "connection" in locals():
                connection.close()

        if candidate_row is None:
            raise PromotedModelResolutionError(
                "Promoted production model has no candidate record."
            )
        try:
            candidate = ModelCandidate.model_validate_json(
                candidate_row["metadata_json"]
            )
        except ValidationError as exc:
            raise PromotedModelResolutionError(
                "Promoted candidate metadata is invalid."
            ) from exc
        if candidate.model_version != state["active_version"]:
            raise PromotedModelResolutionError(
                "Promoted candidate identity is inconsistent."
            )
        return PromotedModelSelection.from_candidate(
            candidate,
            repository_root=self.repository_root,
        )


def validate_selected_package(
    selection: PromotedModelSelection,
    package: ProductionModelPackage,
) -> None:
    """Ensure loader output still matches immutable registry lineage."""
    lineage = package.lineage
    if any(
        (
            package.package_id != selection.package_id,
            lineage.dataset_name != selection.dataset_name,
            lineage.dataset_category != selection.dataset_category,
            lineage.dataset_version != selection.dataset_version,
            lineage.manifest_fingerprint != selection.manifest_fingerprint,
            lineage.feature_bank_sha256 != selection.feature_bank_sha256,
        )
    ):
        raise PromotedModelResolutionError(
            "Loaded package lineage does not match promoted registry metadata."
        )
