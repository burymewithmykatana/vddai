from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_DATASET_ROOT = (
    PROJECT_ROOT / "data" / "raw" / "mvtec_ad" / "tile"
)

DEFAULT_METADATA_PATH = (
    PROJECT_ROOT / "data" / "metadata" / "mvtec_ad_tile.json"
)

EXPECTED_DIRECTORIES = (
    "train",
    "test",
    "ground_truth",
)


class AcquisitionError(RuntimeError):
    """Raised when dataset acquisition cannot be completed safely."""


def calculate_sha256(file_path: Path) -> str:
    """Calculate the SHA-256 digest of a file."""

    digest = hashlib.sha256()

    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def locate_tile_directory(extraction_root: Path) -> Path:
    """
    Locate the extracted MVTec AD tile category.

    Supports both:
    - archive/tile/train/...
    - archive/mvtec_anomaly_detection/tile/train/...
    """

    candidates: list[Path] = []

    for candidate in extraction_root.rglob("tile"):
        if not candidate.is_dir():
            continue

        if all(
            (candidate / directory).is_dir()
            for directory in EXPECTED_DIRECTORIES
        ):
            candidates.append(candidate)

    if not candidates:
        raise AcquisitionError(
            "Could not find a valid 'tile' directory containing "
            "'train', 'test', and 'ground_truth'."
        )

    if len(candidates) > 1:
        formatted = "\n".join(
            f"- {candidate}" for candidate in candidates
        )
        raise AcquisitionError(
            "Multiple valid tile directories were found:\n"
            f"{formatted}"
        )

    return candidates[0]


def safely_extract_tar(archive_path: Path, destination: Path) -> None:
    """Extract a tar archive while preventing path traversal."""

    destination = destination.resolve()

    with tarfile.open(archive_path, mode="r:*") as archive:
        for member in archive.getmembers():
            member_path = (destination / member.name).resolve()

            try:
                member_path.relative_to(destination)
            except ValueError as exc:
                raise AcquisitionError(
                    f"Unsafe archive member path: {member.name}"
                ) from exc

        archive.extractall(destination)


def update_metadata(
    metadata_path: Path,
    archive_path: Path,
    archive_sha256: str,
) -> None:
    """Update tracked dataset acquisition metadata."""

    if not metadata_path.exists():
        raise AcquisitionError(
            f"Metadata file does not exist: {metadata_path}"
        )

    with metadata_path.open("r", encoding="utf-8") as file:
        metadata = json.load(file)

    metadata["acquisition_date"] = datetime.now(UTC).date().isoformat()
    metadata["archive_filename"] = archive_path.name
    metadata["archive_sha256"] = archive_sha256
    metadata["acquisition_method"] = "official-manual-download"
    metadata["license"] = "CC BY-NC-SA 4.0"
    metadata["commercial_use_allowed"] = False

    with metadata_path.open("w", encoding="utf-8") as file:
        json.dump(
            metadata,
            file,
            indent=2,
            ensure_ascii=False,
        )
        file.write("\n")


def acquire_dataset(
    archive_path: Path,
    dataset_root: Path,
    metadata_path: Path,
    force: bool,
) -> None:
    """Validate, extract, install, and record the tile dataset."""

    archive_path = archive_path.resolve()
    dataset_root = dataset_root.resolve()
    metadata_path = metadata_path.resolve()

    if not archive_path.is_file():
        raise AcquisitionError(
            f"Archive does not exist: {archive_path}"
        )

    if dataset_root.exists() and not force:
        raise AcquisitionError(
            f"Dataset destination already exists: {dataset_root}\n"
            "Use --force only when you intentionally want to replace it."
        )

    archive_sha256 = calculate_sha256(archive_path)

    print(f"Archive: {archive_path}")
    print(f"SHA-256: {archive_sha256}")

    with tempfile.TemporaryDirectory(
        prefix="vddai-mvtec-"
    ) as temporary_directory:
        extraction_root = Path(temporary_directory)

        print("Extracting archive...")
        safely_extract_tar(archive_path, extraction_root)

        tile_source = locate_tile_directory(extraction_root)

        if dataset_root.exists():
            shutil.rmtree(dataset_root)

        dataset_root.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        shutil.copytree(tile_source, dataset_root)

    update_metadata(
        metadata_path=metadata_path,
        archive_path=archive_path,
        archive_sha256=archive_sha256,
    )

    print(f"Installed tile dataset at: {dataset_root}")
    print(f"Updated metadata at: {metadata_path}")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Install the MVTec AD tile category from an "
            "officially downloaded archive."
        )
    )

    parser.add_argument(
        "--archive",
        required=True,
        type=Path,
        help="Path to the officially downloaded MVTec AD tar archive.",
    )

    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=DEFAULT_DATASET_ROOT,
        help="Destination directory for the extracted tile category.",
    )

    parser.add_argument(
        "--metadata",
        type=Path,
        default=DEFAULT_METADATA_PATH,
        help="Tracked metadata JSON file.",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing local tile dataset.",
    )

    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()

    try:
        acquire_dataset(
            archive_path=arguments.archive,
            dataset_root=arguments.dataset_root,
            metadata_path=arguments.metadata,
            force=arguments.force,
        )
    except (
        AcquisitionError,
        json.JSONDecodeError,
        tarfile.TarError,
        OSError,
    ) as exc:
        raise SystemExit(f"Acquisition failed: {exc}") from exc


if __name__ == "__main__":
    main()