"""Render the approved single-host HTTPS staging Compose configuration.

This command deliberately provisions nothing. It validates the non-versioned
host configuration and delegates application image validation to the W8D2
immutable Compose boundary before invoking Docker Compose.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

try:
    from scripts.run_immutable_compose import (
        ImmutableComposeValidationError,
        immutable_artifacts_path_from_environment,
        immutable_image_reference_from_environment,
    )
except ModuleNotFoundError:  # Direct `python scripts/run_staging_compose.py` use.
    from run_immutable_compose import (  # type: ignore[no-redef]
        ImmutableComposeValidationError,
        immutable_artifacts_path_from_environment,
        immutable_image_reference_from_environment,
    )

STAGING_ENV_FILE_ENVIRONMENT_VARIABLE = "VDDAI_STAGING_ENV_FILE"
STAGING_FQDN_ENVIRONMENT_VARIABLE = "VDDAI_STAGING_FQDN"
POSTGRES_IMAGE_ENVIRONMENT_VARIABLE = "VDDAI_POSTGRES_IMAGE"
REDIS_IMAGE_ENVIRONMENT_VARIABLE = "VDDAI_REDIS_IMAGE"
CADDY_IMAGE_ENVIRONMENT_VARIABLE = "VDDAI_CADDY_IMAGE"
STAGING_COMPOSE_PROJECT_NAME = "vddai-staging"
_IMAGE_REFERENCE_PATTERN = re.compile(
    r"^[a-z0-9][a-z0-9._-]*(?::[0-9]+)?(?:/[a-z0-9][a-z0-9._-]*)*"
    r"@sha256:[0-9a-f]{64}$"
)
_FQDN_PATTERN = re.compile(
    r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?",
    re.IGNORECASE,
)
_REQUIRED_SETTINGS = {
    "ENVIRONMENT",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "DATABASE_URL",
    "REDIS_URL",
    "JWT_SECRET_KEY",
    "IMAGE_STORAGE_BACKEND",
    "IMAGE_STORAGE_ROOT",
    "MODEL_REGISTRY_PATH",
    "MODEL_ARTIFACT_ROOT",
}
_ALLOWED_SETTINGS = _REQUIRED_SETTINGS | {
    "PROJECT_NAME",
    "JWT_EXPIRE_MINUTES",
    "MAX_IMAGE_SIZE_MB",
    "MAX_IMAGE_PIXELS",
    "PREDICTION_RATE_LIMIT_REQUESTS",
    "PREDICTION_RATE_LIMIT_WINDOW_SECONDS",
    "PREDICTION_USER_OUTSTANDING_LIMIT",
    "PREDICTION_GLOBAL_OUTSTANDING_LIMIT",
    "PREDICTION_CAPACITY_RETRY_AFTER_SECONDS",
    "MODEL_IMAGE_WIDTH",
    "MODEL_IMAGE_HEIGHT",
    "MODEL_DEVICE",
    "WORKER_POLL_INTERVAL_SECONDS",
    "WORKER_MAX_ATTEMPTS",
    "WORKER_RETRY_DELAY_SECONDS",
    "WORKER_ATTEMPT_LEASE_SECONDS",
}


class StagingComposeValidationError(ValueError):
    """Raised before Docker Compose runs when staging input is unsafe."""


def _require_digest_reference(value: str | None, *, variable_name: str) -> str:
    if not value or not _IMAGE_REFERENCE_PATTERN.fullmatch(value):
        raise StagingComposeValidationError(
            f"{variable_name} must be a canonical name@sha256:<64-lowercase-hex-digest> "
            "reference."
        )
    return value


def _parse_env_file(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise StagingComposeValidationError(
            "Staging environment file is unreadable."
        ) from exc

    values: dict[str, str] = {}
    for line in lines:
        candidate = line.strip()
        if not candidate or candidate.startswith("#"):
            continue
        if "=" not in candidate:
            raise StagingComposeValidationError(
                "Staging environment file contains an invalid assignment."
            )
        key, value = candidate.split("=", maxsplit=1)
        if not key or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise StagingComposeValidationError(
                "Staging environment file contains an invalid setting name."
            )
        if key in values:
            raise StagingComposeValidationError(
                "Staging environment file contains a duplicate setting."
            )
        values[key] = value
    return values


def staging_env_file_from_environment(
    environ: Mapping[str, str] | None = None,
    *,
    repository_root: Path | None = None,
) -> Path:
    effective_environ = os.environ if environ is None else environ
    configured_path = effective_environ.get(STAGING_ENV_FILE_ENVIRONMENT_VARIABLE)
    if not configured_path:
        raise StagingComposeValidationError(
            f"{STAGING_ENV_FILE_ENVIRONMENT_VARIABLE} must name a host-managed "
            "staging environment file."
        )
    path = Path(configured_path).expanduser().resolve()
    if not path.is_file():
        raise StagingComposeValidationError("Staging environment file is missing.")
    root = (repository_root or Path(__file__).resolve().parents[1]).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return path
    raise StagingComposeValidationError(
        "Staging environment file must be outside the repository."
    )


def validate_staging_settings(values: Mapping[str, str]) -> None:
    if values.keys() - _ALLOWED_SETTINGS:
        raise StagingComposeValidationError(
            "Staging environment file contains unsupported settings."
        )
    # Support one literal dotenv subset, not a second interpolation language.
    # Compose must deliver exactly the values that were validated here.
    if any(
        any(ord(character) < 33 or ord(character) > 126 for character in value)
        or any(character in value for character in "\"'$#\\")
        for value in values.values()
    ):
        raise StagingComposeValidationError(
            "Staging settings must be unquoted printable ASCII literals without "
            "whitespace, dollar signs, hash signs, or backslashes."
        )
    missing = sorted(
        setting for setting in _REQUIRED_SETTINGS if not values.get(setting)
    )
    if missing:
        raise StagingComposeValidationError(
            "Staging environment file is missing required settings."
        )
    if values["ENVIRONMENT"] != "staging":
        raise StagingComposeValidationError("ENVIRONMENT must be exactly staging.")
    if values["JWT_SECRET_KEY"] == "change-this-secret" or values[
        "JWT_SECRET_KEY"
    ].startswith("replace-"):
        raise StagingComposeValidationError(
            "JWT_SECRET_KEY must not use a development or template value."
        )
    if any(
        values[name].startswith("replace-")
        for name in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")
    ):
        raise StagingComposeValidationError(
            "PostgreSQL settings must not use template values."
        )
    if (
        values["IMAGE_STORAGE_BACKEND"] != "local"
        or values["IMAGE_STORAGE_ROOT"] != "uploads"
    ):
        raise StagingComposeValidationError(
            "Staging must retain the approved local uploads storage boundary."
        )
    if (
        values["MODEL_REGISTRY_PATH"] != "artifacts/registry/model_registry.sqlite3"
        or values["MODEL_ARTIFACT_ROOT"] != "."
    ):
        raise StagingComposeValidationError(
            "Staging must retain the approved registry-selected artifact paths."
        )
    if any(
        not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", values[name])
        for name in ("POSTGRES_USER", "POSTGRES_DB")
    ):
        raise StagingComposeValidationError(
            "PostgreSQL user and database must be simple ASCII identifiers."
        )
    # The existing Alembic ConfigParser handoff cannot accept percent escapes.
    # Restrict staging credentials instead of changing the migration boundary.
    if not re.fullmatch(r"[A-Za-z0-9._~-]+", values["POSTGRES_PASSWORD"]):
        raise StagingComposeValidationError(
            "POSTGRES_PASSWORD must contain only ASCII letters, digits, or -._~ "
            "for compatibility with migration startup."
        )
    expected_database_url = (
        f"postgresql+psycopg://{values['POSTGRES_USER']}:"
        f"{values['POSTGRES_PASSWORD']}"
        f"@postgres:5432/{values['POSTGRES_DB']}"
    )
    if values["DATABASE_URL"] != expected_database_url:
        raise StagingComposeValidationError(
            "DATABASE_URL must use the canonical internal postgres:5432 URL "
            "with matching bootstrap credentials and no connection options."
        )
    if values["REDIS_URL"] != "redis://redis:6379/0":
        raise StagingComposeValidationError(
            "REDIS_URL must target the internal Redis service."
        )


def staging_fqdn_from_environment(environ: Mapping[str, str] | None = None) -> str:
    effective_environ = os.environ if environ is None else environ
    fqdn = effective_environ.get(STAGING_FQDN_ENVIRONMENT_VARIABLE, "")
    if not _FQDN_PATTERN.fullmatch(fqdn):
        raise StagingComposeValidationError(
            f"{STAGING_FQDN_ENVIRONMENT_VARIABLE} must be a public DNS hostname."
        )
    return fqdn.lower()


def staging_compose_document(
    *,
    application_image: str,
    artifacts_path: str,
    environment_file: Path,
    fqdn: str,
    settings: Mapping[str, str],
    postgres_image: str,
    redis_image: str,
    caddy_image: str,
) -> dict[str, Any]:
    artifact_mount = f"{artifacts_path}:/app/artifacts:ro"
    caddyfile = Path(__file__).resolve().parents[1] / "deploy" / "staging" / "Caddyfile"
    return {
        "name": STAGING_COMPOSE_PROJECT_NAME,
        "services": {
            "api": {
                "image": application_image,
                "env_file": [str(environment_file)],
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
                        "urllib.request.urlopen('http://localhost:8000/health', timeout=2); "
                        "urllib.request.urlopen('http://localhost:8000/health/model', timeout=2)",
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
                "image": application_image,
                "env_file": [str(environment_file)],
                "environment": {"TORCH_HOME": "/app/artifacts/weights"},
                "command": ["python", "-m", "app.workers.prediction_worker"],
                "volumes": ["vddai_uploads:/app/uploads", artifact_mount],
                "depends_on": {"api": {"condition": "service_healthy"}},
            },
            "postgres": {
                "image": postgres_image,
                "environment": {
                    "POSTGRES_USER": settings["POSTGRES_USER"],
                    "POSTGRES_PASSWORD": settings["POSTGRES_PASSWORD"],
                    "POSTGRES_DB": settings["POSTGRES_DB"],
                },
                "volumes": ["postgres_data:/var/lib/postgresql/data"],
                "healthcheck": {
                    "test": [
                        "CMD-SHELL",
                        "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}",
                    ],
                    "interval": "5s",
                    "timeout": "3s",
                    "retries": 12,
                },
            },
            "redis": {
                "image": redis_image,
                "healthcheck": {
                    "test": ["CMD", "redis-cli", "ping"],
                    "interval": "5s",
                    "timeout": "3s",
                    "retries": 12,
                },
            },
            "caddy": {
                "image": caddy_image,
                "ports": ["80:80", "443:443"],
                "environment": {"STAGING_FQDN": fqdn},
                "volumes": [
                    f"{caddyfile}:/etc/caddy/Caddyfile:ro",
                    "caddy_data:/data",
                    "caddy_config:/config",
                ],
                "depends_on": {"api": {"condition": "service_healthy"}},
            },
        },
        "volumes": {
            "postgres_data": None,
            "vddai_uploads": None,
            "caddy_data": None,
            "caddy_config": None,
        },
    }


def run_staging_compose(
    compose_arguments: Sequence[str], *, environ: Mapping[str, str] | None = None
) -> int:
    if not compose_arguments:
        raise StagingComposeValidationError("Provide a Docker Compose subcommand.")
    effective_environ = os.environ if environ is None else environ
    environment_file = staging_env_file_from_environment(effective_environ)
    settings = _parse_env_file(environment_file)
    validate_staging_settings(settings)
    artifacts_path = immutable_artifacts_path_from_environment(effective_environ)
    if not (
        Path(artifacts_path).is_absolute()
        or PurePosixPath(artifacts_path).is_absolute()
    ):
        raise StagingComposeValidationError(
            "VDDAI_ARTIFACTS_PATH must be an absolute host path."
        )
    document = staging_compose_document(
        application_image=immutable_image_reference_from_environment(effective_environ),
        artifacts_path=artifacts_path,
        environment_file=environment_file,
        fqdn=staging_fqdn_from_environment(effective_environ),
        settings=settings,
        postgres_image=_require_digest_reference(
            effective_environ.get(POSTGRES_IMAGE_ENVIRONMENT_VARIABLE),
            variable_name=POSTGRES_IMAGE_ENVIRONMENT_VARIABLE,
        ),
        redis_image=_require_digest_reference(
            effective_environ.get(REDIS_IMAGE_ENVIRONMENT_VARIABLE),
            variable_name=REDIS_IMAGE_ENVIRONMENT_VARIABLE,
        ),
        caddy_image=_require_digest_reference(
            effective_environ.get(CADDY_IMAGE_ENVIRONMENT_VARIABLE),
            variable_name=CADDY_IMAGE_ENVIRONMENT_VARIABLE,
        ),
    )
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--project-name",
            STAGING_COMPOSE_PROJECT_NAME,
            "-f",
            "-",
            *compose_arguments,
        ],
        check=False,
        input=json.dumps(document),
        text=True,
    )
    return result.returncode


def parse_args(argv: Sequence[str] | None = None) -> list[str]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compose_arguments", nargs=argparse.REMAINDER)
    return parser.parse_args(argv).compose_arguments


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return run_staging_compose(parse_args(argv))
    except (ImmutableComposeValidationError, StagingComposeValidationError) as exc:
        print(f"Staging Compose validation failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
