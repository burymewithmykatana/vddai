"""Validate a digest-pinned application image before invoking immutable Compose."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections.abc import Mapping, Sequence
from typing import Any

IMMUTABLE_IMAGE_ENVIRONMENT_VARIABLE = "VDDAI_APPLICATION_IMAGE"
IMMUTABLE_ARTIFACTS_ENVIRONMENT_VARIABLE = "VDDAI_ARTIFACTS_PATH"
IMMUTABLE_IMAGE_REFERENCE_PATTERN = re.compile(
    r"^[a-z0-9][a-z0-9._-]*(?::[0-9]+)?(?:/[a-z0-9][a-z0-9._-]*)*"
    r"@sha256:[0-9a-f]{64}$"
)
IMMUTABLE_COMPOSE_FILE = "-"


class ImmutableComposeValidationError(ValueError):
    """Raised when the deployment-oriented image reference is not immutable."""


def validate_immutable_image_reference(
    image_reference: str | None,
) -> str:
    """Require a canonical repository-qualified SHA-256 image reference."""
    if not image_reference or not IMMUTABLE_IMAGE_REFERENCE_PATTERN.fullmatch(
        image_reference
    ):
        raise ImmutableComposeValidationError(
            f"{IMMUTABLE_IMAGE_ENVIRONMENT_VARIABLE} must be a canonical "
            "name@sha256:<64-lowercase-hex-digest> reference."
        )
    return image_reference


def immutable_image_reference_from_environment(
    environ: Mapping[str, str] | None = None,
) -> str:
    """Read and validate the one image reference shared by API and worker."""
    effective_environ = os.environ if environ is None else environ
    return validate_immutable_image_reference(
        effective_environ.get(IMMUTABLE_IMAGE_ENVIRONMENT_VARIABLE)
    )


def immutable_artifacts_path_from_environment(
    environ: Mapping[str, str] | None = None,
) -> str:
    """Require the host directory for explicitly provisioned runtime artifacts."""
    effective_environ = os.environ if environ is None else environ
    artifacts_path = effective_environ.get(IMMUTABLE_ARTIFACTS_ENVIRONMENT_VARIABLE)
    if not artifacts_path:
        raise ImmutableComposeValidationError(
            f"{IMMUTABLE_ARTIFACTS_ENVIRONMENT_VARIABLE} must name the "
            "provisioned runtime artifacts directory."
        )
    return artifacts_path


def immutable_compose_document(
    image_reference: str,
    artifacts_path: str,
) -> dict[str, Any]:
    """Build the only deployment-oriented Compose document after validation."""
    artifact_mount = f"{artifacts_path}:/app/artifacts:ro"
    return {
        "services": {
            "api": {
                "image": image_reference,
                "ports": ["8000:8000"],
                "env_file": [".env"],
                "environment": {"TORCH_HOME": "/app/artifacts/weights"},
                "command": (
                    'sh -c "alembic upgrade head && exec uvicorn app.main:app '
                    '--host 0.0.0.0 --port 8000"'
                ),
                "healthcheck": {
                    "test": [
                        "CMD",
                        "python",
                        "-c",
                        "import urllib.request; "
                        "urllib.request.urlopen('http://localhost:8000/health', "
                        "timeout=2)",
                    ],
                    "interval": "5s",
                    "timeout": "3s",
                    "retries": 12,
                },
                "volumes": ["vddai_uploads:/app/uploads", artifact_mount],
                "depends_on": {
                    "postgres": {"condition": "service_healthy"},
                    "redis": {"condition": "service_healthy"},
                },
            },
            "worker": {
                "image": image_reference,
                "env_file": [".env"],
                "environment": {"TORCH_HOME": "/app/artifacts/weights"},
                "command": ["python", "-m", "app.workers.prediction_worker"],
                "volumes": ["vddai_uploads:/app/uploads", artifact_mount],
                "depends_on": {"api": {"condition": "service_healthy"}},
            },
            "postgres": {
                "image": "postgres:16",
                "environment": {
                    "POSTGRES_USER": "postgres",
                    "POSTGRES_PASSWORD": "postgres",
                    "POSTGRES_DB": "vision_ai",
                },
                "ports": ["5432:5432"],
                "volumes": ["postgres_data:/var/lib/postgresql/data"],
                "healthcheck": {
                    "test": ["CMD-SHELL", "pg_isready -U postgres -d vision_ai"],
                    "interval": "5s",
                    "timeout": "3s",
                    "retries": 12,
                },
            },
            "redis": {
                "image": "redis:7",
                "ports": ["6379:6379"],
                "healthcheck": {
                    "test": ["CMD", "redis-cli", "ping"],
                    "interval": "5s",
                    "timeout": "3s",
                    "retries": 12,
                },
            },
        },
        "volumes": {"postgres_data": None, "vddai_uploads": None},
    }


def immutable_compose_command(compose_arguments: Sequence[str]) -> list[str]:
    """Build the repository's deployment-oriented Compose command."""
    if not compose_arguments:
        raise ImmutableComposeValidationError(
            "Provide a docker compose subcommand, such as 'config --quiet' or 'up -d'."
        )
    return [
        "docker",
        "compose",
        "-f",
        IMMUTABLE_COMPOSE_FILE,
        *compose_arguments,
    ]


def run_immutable_compose(
    compose_arguments: Sequence[str],
    *,
    environ: Mapping[str, str] | None = None,
) -> int:
    """Fail before Compose runs unless the shared image is digest-pinned."""
    image_reference = immutable_image_reference_from_environment(environ)
    artifacts_path = immutable_artifacts_path_from_environment(environ)
    result = subprocess.run(
        immutable_compose_command(compose_arguments),
        check=False,
        input=json.dumps(immutable_compose_document(image_reference, artifacts_path)),
        text=True,
    )
    return result.returncode


def parse_args(argv: Sequence[str] | None = None) -> list[str]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compose_arguments", nargs=argparse.REMAINDER)
    return parser.parse_args(argv).compose_arguments


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return run_immutable_compose(parse_args(argv))
    except ImmutableComposeValidationError as exc:
        print(f"Immutable Compose validation failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
