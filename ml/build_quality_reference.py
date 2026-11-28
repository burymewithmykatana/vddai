"""Build a quality baseline from the frozen package's normal validation split."""

import argparse
from collections import Counter
from math import ceil, fsum
from pathlib import Path, PurePosixPath

from app.contracts.inference import PredictionLabel
from app.services.anomaly_inference_service import AnomalyInferenceService
from app.services.model_package_loader import ModelPackageLoader, ProductionModelPackage
from app.services.quality_monitor import (
    FORMATS,
    MIN_OBSERVATIONS,
    QualityReference,
    image_quality,
    quality_observer,
)
from ml.data.build_manifest import DatasetManifest, read_json_manifest
from ml.data.process_manifest import resolve_manifest_path
from ml.generate_feature_bank import calculate_manifest_fingerprint


def _require_disjoint_manifest(manifest: DatasetManifest, root: Path) -> None:
    sample_ids: set[str] = set()
    paths: set[Path] = set()
    for record in manifest.records:
        if record.sample_id in sample_ids:
            raise ValueError("Duplicate manifest sample identity.")
        sample_ids.add(record.sample_id)

        relative_path = Path(record.image_path)
        if relative_path.anchor or ".." in relative_path.parts:
            raise ValueError("Manifest image path is outside the dataset root.")
        # Check aliases without requiring or opening official test images.
        path = (root / relative_path).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Manifest image path is outside the dataset root.")
        if path in paths:
            raise ValueError("Duplicate manifest image path.")
        paths.add(path)


def build_reference(
    package: ProductionModelPackage,
    manifest: DatasetManifest,
    dataset_root: Path,
) -> QualityReference:
    lineage = package.lineage
    fingerprint = calculate_manifest_fingerprint(manifest)
    if (
        manifest.dataset_name != lineage.dataset_name
        or manifest.category != lineage.dataset_category
        or manifest.dataset_version != lineage.dataset_version
        or fingerprint != lineage.manifest_fingerprint
    ):
        raise ValueError("Validation manifest does not match the frozen package.")

    root = dataset_root.resolve()
    _require_disjoint_manifest(manifest, root)
    normal_root = root / "train" / "good"
    validation = [record for record in manifest.records if record.split == "validation"]
    if len(validation) < MIN_OBSERVATIONS:
        raise ValueError("Insufficient normal validation records.")
    paths = []
    for record in validation:
        if (
            record.is_anomaly is not False
            or record.label != 0
            or record.class_name != "good"
            or record.mask_path is not None
            or PurePosixPath(record.image_path).parts[:2] != ("train", "good")
        ):
            raise ValueError("A validation record is outside the normal split.")
        path = resolve_manifest_path(root, record.image_path)
        if not path.is_relative_to(normal_root):
            raise ValueError("A validation image resolves outside the normal split.")
        paths.append(path)
    service = AnomalyInferenceService(package=package)
    measurements, scores = [], []
    formats = Counter(dict.fromkeys(FORMATS, 0))
    anomaly_count = 0

    def measure(preprocessed, _result):
        measurements.append((image_quality(preprocessed), preprocessed.original_mode))

    token = quality_observer.set(measure)
    try:
        for path, record in zip(paths, validation, strict=True):
            result = service.predict(path)
            scores.append(result.anomaly_score)
            if len(measurements) != len(scores):
                raise ValueError("A quality observation is missing.")
            image, source_mode = measurements[-1]
            if (
                image.width != record.width
                or image.height != record.height
                or image.format != record.image_format.lower()
                or source_mode != record.mode
            ):
                raise ValueError("Validation image metadata differs from the manifest.")
            formats[image.format] += 1
            anomaly_count += result.predicted_label == PredictionLabel.ANOMALOUS
    finally:
        quality_observer.reset(token)

    count = len(validation)
    return QualityReference(
        schema_version="vddai.quality_reference.v1",
        source="normal_validation",
        package_id=package.package_id,
        manifest_fingerprint=fingerprint,
        preprocessing_version=lineage.preprocessing_schema_version,
        count=count,
        format_counts=dict(formats),
        pixel_mean=fsum(image.mean for image, _ in measurements) / count,
        pixel_contrast=fsum(image.contrast for image, _ in measurements) / count,
        anomaly_count=anomaly_count,
        score_p95=sorted(scores)[ceil(0.95 * count) - 1],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-manifest", required=True, type=Path)
    parser.add_argument("--feature-bank", required=True, type=Path)
    parser.add_argument("--dataset-manifest", required=True, type=Path)
    parser.add_argument("--dataset-root", required=True, type=Path)
    args = parser.parse_args()
    package = ModelPackageLoader(
        package_manifest_path=args.package_manifest,
        feature_bank_dir=args.feature_bank,
    ).load()
    reference = build_reference(
        package, read_json_manifest(args.dataset_manifest), args.dataset_root
    )
    print(reference.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
