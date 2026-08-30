"""Validate the source-identity labels on one locally available image."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Mapping
from typing import Any

OCI_SOURCE_LABEL = "org.opencontainers.image.source"
OCI_REVISION_LABEL = "org.opencontainers.image.revision"
OCI_VERSION_LABEL = "org.opencontainers.image.version"
FULL_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class ImmutableImageValidationError(RuntimeError):
    """Raised when an image cannot prove its required immutable identity."""


def inspect_image(image: str) -> Mapping[str, Any]:
    """Return Docker inspection metadata for one local image reference."""
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", image],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = ""
        if isinstance(exc, subprocess.CalledProcessError):
            detail = (exc.stderr or "").strip()
        message = f"Docker image inspection failed for {image!r}"
        if detail:
            message += f": {detail}"
        raise ImmutableImageValidationError(message) from exc

    try:
        records = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ImmutableImageValidationError(
            f"Docker returned invalid image inspection JSON for {image!r}."
        ) from exc
    if not isinstance(records, list) or len(records) != 1:
        raise ImmutableImageValidationError(
            f"Docker did not return exactly one image record for {image!r}."
        )
    record = records[0]
    if not isinstance(record, Mapping):
        raise ImmutableImageValidationError(
            f"Docker returned an invalid image record for {image!r}."
        )
    return record


def validate_image_identity(
    image: str,
    *,
    source: str,
    revision: str,
    version: str,
) -> str:
    """Require OCI labels and a local immutable image ID for one build."""
    if not FULL_SHA_PATTERN.fullmatch(revision):
        raise ImmutableImageValidationError(
            "Expected revision must be a full lowercase SHA."
        )
    record = inspect_image(image)
    image_id = record.get("Id")
    if not isinstance(image_id, str) or not image_id.startswith("sha256:"):
        raise ImmutableImageValidationError(
            "Image inspection did not return a sha256 image ID."
        )

    config = record.get("Config")
    labels = config.get("Labels") if isinstance(config, Mapping) else None
    if not isinstance(labels, Mapping):
        raise ImmutableImageValidationError("Image has no OCI source-identity labels.")
    expected_labels = {
        OCI_SOURCE_LABEL: source,
        OCI_REVISION_LABEL: revision,
        OCI_VERSION_LABEL: version,
    }
    mismatches = [
        f"{label}={labels.get(label)!r}"
        for label, expected in expected_labels.items()
        if labels.get(label) != expected
    ]
    if mismatches:
        raise ImmutableImageValidationError(
            "Image source-identity labels do not match: " + ", ".join(mismatches)
        )
    return image_id


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image", required=True, help="Local image tag or ID to inspect."
    )
    parser.add_argument("--source", required=True, help="Expected OCI source URL.")
    parser.add_argument("--revision", required=True, help="Expected full source SHA.")
    parser.add_argument("--version", required=True, help="Expected OCI image version.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        image_id = validate_image_identity(
            args.image,
            source=args.source,
            revision=args.revision,
            version=args.version,
        )
    except ImmutableImageValidationError as exc:
        print(f"Immutable image validation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Immutable image validation passed: image_id={image_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
