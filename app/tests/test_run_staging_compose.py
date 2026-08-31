import json
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote

import pytest
from alembic.config import Config
from sqlalchemy.dialects.postgresql.psycopg import PGDialect_psycopg
from sqlalchemy.engine import make_url

from scripts import run_staging_compose


def _digest(name: str, character: str) -> str:
    return f"{name}@sha256:{character * 64}"


def _staging_environment(env_file: Path) -> dict[str, str]:
    return {
        "VDDAI_STAGING_ENV_FILE": str(env_file),
        "VDDAI_STAGING_FQDN": "staging.vddai.example",
        "VDDAI_APPLICATION_IMAGE": _digest("ghcr.io/example/vddai", "a"),
        "VDDAI_ARTIFACTS_PATH": "/srv/vddai/artifacts",
        "VDDAI_POSTGRES_IMAGE": _digest("docker.io/library/postgres", "b"),
        "VDDAI_REDIS_IMAGE": _digest("docker.io/library/redis", "c"),
        "VDDAI_CADDY_IMAGE": _digest("docker.io/library/caddy", "d"),
    }


def _write_staging_environment(path: Path, *, jwt_secret: str = "safe-secret") -> None:
    path.write_text(
        "\n".join(
            [
                "ENVIRONMENT=staging",
                "POSTGRES_USER=staging_user",
                "POSTGRES_PASSWORD=staging_password",
                "POSTGRES_DB=staging_db",
                "DATABASE_URL=postgresql+psycopg://staging_user:staging_password@postgres:5432/staging_db",
                "REDIS_URL=redis://redis:6379/0",
                f"JWT_SECRET_KEY={jwt_secret}",
                "IMAGE_STORAGE_BACKEND=local",
                "IMAGE_STORAGE_ROOT=uploads",
                "MODEL_REGISTRY_PATH=artifacts/registry/model_registry.sqlite3",
                "MODEL_ARTIFACT_ROOT=.",
            ]
        ),
        encoding="utf-8",
    )


def test_staging_compose_uses_immutable_images_and_internal_dependencies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / "staging.env"
    _write_staging_environment(env_file)
    observed_document: str | None = None

    def fake_run(
        command: list[str], *, check: bool, input: str, text: bool
    ) -> subprocess.CompletedProcess[str]:
        nonlocal observed_document
        assert command == [
            "docker",
            "compose",
            "--project-name",
            "vddai-staging",
            "-f",
            "-",
            "config",
            "--quiet",
        ]
        assert check is False
        assert text is True
        observed_document = input
        return subprocess.CompletedProcess(command, returncode=0)

    monkeypatch.setattr(run_staging_compose.subprocess, "run", fake_run)
    monkeypatch.setattr(
        run_staging_compose,
        "staging_env_file_from_environment",
        lambda _environ: env_file,
    )

    assert (
        run_staging_compose.run_staging_compose(
            ["config", "--quiet"], environ=_staging_environment(env_file)
        )
        == 0
    )
    assert observed_document is not None
    assert '"name": "vddai-staging"' in observed_document
    assert '"image": "ghcr.io/example/vddai@sha256:' in observed_document
    assert '"ports": ["5432:5432"]' not in observed_document
    assert '"ports": ["6379:6379"]' not in observed_document
    assert '"ports": ["80:80", "443:443"]' in observed_document
    assert '"read_only"' not in observed_document
    assert "/app/artifacts:ro" in observed_document
    assert "http://localhost:8000/health/model" in observed_document
    assert ".:/app" not in observed_document


@pytest.mark.parametrize(
    ("environment_key", "value"),
    [
        ("VDDAI_APPLICATION_IMAGE", "ghcr.io/example/vddai:latest"),
        ("VDDAI_POSTGRES_IMAGE", "postgres:16"),
        ("VDDAI_REDIS_IMAGE", "redis:7"),
        ("VDDAI_CADDY_IMAGE", "caddy:2"),
    ],
)
def test_staging_compose_rejects_mutable_images_before_compose_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    environment_key: str,
    value: str,
) -> None:
    env_file = tmp_path / "staging.env"
    _write_staging_environment(env_file)
    environment = _staging_environment(env_file)
    environment[environment_key] = value

    def fail_if_compose_runs(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Compose must not run with a mutable image.")

    monkeypatch.setattr(run_staging_compose.subprocess, "run", fail_if_compose_runs)
    monkeypatch.setattr(
        run_staging_compose,
        "staging_env_file_from_environment",
        lambda _environ: env_file,
    )

    with pytest.raises(
        (
            run_staging_compose.ImmutableComposeValidationError,
            run_staging_compose.StagingComposeValidationError,
        ),
    ):
        run_staging_compose.run_staging_compose(
            ["config", "--quiet"], environ=environment
        )


def test_staging_compose_rejects_template_secret_before_compose_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / "staging.env"
    _write_staging_environment(
        env_file, jwt_secret="replace-with-a-unique-high-entropy-staging-secret"
    )

    def fail_if_compose_runs(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Compose must not run with a template secret.")

    monkeypatch.setattr(run_staging_compose.subprocess, "run", fail_if_compose_runs)
    monkeypatch.setattr(
        run_staging_compose,
        "staging_env_file_from_environment",
        lambda _environ: env_file,
    )

    with pytest.raises(run_staging_compose.StagingComposeValidationError):
        run_staging_compose.run_staging_compose(
            ["config", "--quiet"], environ=_staging_environment(env_file)
        )


def test_staging_compose_requires_an_absolute_artifact_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / "staging.env"
    _write_staging_environment(env_file)
    environment = _staging_environment(env_file)
    environment["VDDAI_ARTIFACTS_PATH"] = "artifacts"

    monkeypatch.setattr(
        run_staging_compose,
        "staging_env_file_from_environment",
        lambda _environ: env_file,
    )

    with pytest.raises(
        run_staging_compose.StagingComposeValidationError,
        match="absolute host path",
    ):
        run_staging_compose.run_staging_compose(
            ["config", "--quiet"], environ=environment
        )


def test_staging_environment_file_must_be_host_managed(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    repository_env_file = repository_root / "staging.env"
    repository_env_file.write_text("ENVIRONMENT=staging\n", encoding="utf-8")
    try:
        with pytest.raises(run_staging_compose.StagingComposeValidationError):
            run_staging_compose.staging_env_file_from_environment(
                {"VDDAI_STAGING_ENV_FILE": str(repository_env_file)},
                repository_root=repository_root,
            )
    finally:
        repository_env_file.unlink()


@pytest.mark.parametrize(
    "jwt_secret",
    [
        "'change-this-secret'",
        '"change-this-secret"',
        "'replace-with-a-unique-high-entropy-staging-secret'",
        "${VDDAI_REVIEW_UNSET_JWT}",
        "$UNSET",
        "",
        "change-this-secret",
        "safe # comment",
        "safe\\nsecret",
        "safe\tsecret",
    ],
)
def test_staging_rejects_unsafe_effective_secrets_before_compose(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, jwt_secret: str
) -> None:
    env_file = tmp_path / "staging.env"
    _write_staging_environment(env_file, jwt_secret=jwt_secret)
    monkeypatch.setattr(
        run_staging_compose,
        "staging_env_file_from_environment",
        lambda _environ: env_file,
    )

    def fail_if_called(*args: object, **kwargs: object) -> None:
        pytest.fail("Invalid settings must not reach Compose")

    monkeypatch.setattr(run_staging_compose.subprocess, "run", fail_if_called)
    with pytest.raises(run_staging_compose.StagingComposeValidationError):
        run_staging_compose.run_staging_compose(
            ["up", "-d"], environ=_staging_environment(env_file)
        )


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql+psycopg://staging_user:staging_password@postgres:5432/staging_db?host=outside.example",
        "postgresql+psycopg://staging_user:staging_password@postgres:5432/staging_db?hostaddr=192.0.2.1",
        "postgresql+psycopg://staging_user:staging_password@postgres:5432/staging_db?service=outside",
        "postgresql+psycopg://staging_user:staging_password@outside.example:5432/staging_db",
        "postgresql+psycopg://staging_user:staging_password@postgres:5433/staging_db",
        "postgresql+psycopg://staging_user:wrong@postgres:5432/staging_db",
        "postgresql+psycopg://staging_user:staging_password@postgres:5432/other_db",
        "postgresql+psycopg://staging_user:staging_password@postgres:5432/staging_db#fragment",
        "not-a-url",
    ],
)
def test_staging_rejects_noncanonical_database_target_before_compose(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, database_url: str
) -> None:
    env_file = tmp_path / "staging.env"
    _write_staging_environment(env_file)
    lines = env_file.read_text().splitlines()
    env_file.write_text(
        "\n".join(
            f"DATABASE_URL={database_url}" if line.startswith("DATABASE_URL=") else line
            for line in lines
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        run_staging_compose,
        "staging_env_file_from_environment",
        lambda _environ: env_file,
    )

    def fail_if_called(*args: object, **kwargs: object) -> None:
        pytest.fail("Invalid database target must not reach Compose")

    monkeypatch.setattr(run_staging_compose.subprocess, "run", fail_if_called)
    with pytest.raises(run_staging_compose.StagingComposeValidationError):
        run_staging_compose.run_staging_compose(
            ["up", "-d"], environ=_staging_environment(env_file)
        )


def test_staging_rejects_duplicate_settings(tmp_path: Path) -> None:
    env_file = tmp_path / "staging.env"
    _write_staging_environment(env_file)
    with env_file.open("a", encoding="utf-8") as stream:
        stream.write("\nJWT_SECRET_KEY=another-secret\n")
    with pytest.raises(run_staging_compose.StagingComposeValidationError):
        run_staging_compose._parse_env_file(env_file)


@pytest.mark.parametrize("setting", ["PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE"])
def test_staging_rejects_libpq_environment_overrides_before_compose(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, setting: str
) -> None:
    env_file = tmp_path / "staging.env"
    _write_staging_environment(env_file)
    with env_file.open("a", encoding="utf-8") as stream:
        stream.write(f"\n{setting}=outside.example\n")
    monkeypatch.setattr(
        run_staging_compose,
        "staging_env_file_from_environment",
        lambda _environ: env_file,
    )

    def fail_if_called(*args: object, **kwargs: object) -> None:
        pytest.fail("libpq overrides must not reach Compose")

    monkeypatch.setattr(run_staging_compose.subprocess, "run", fail_if_called)
    with pytest.raises(run_staging_compose.StagingComposeValidationError):
        run_staging_compose.run_staging_compose(
            ["up", "-d"], environ=_staging_environment(env_file)
        )


@pytest.mark.parametrize("password", ["'review_password'", "${UNSET_PASSWORD}"])
def test_staging_rejects_nonliteral_postgres_password(
    tmp_path: Path, password: str
) -> None:
    env_file = tmp_path / "staging.env"
    _write_staging_environment(env_file)
    settings = run_staging_compose._parse_env_file(env_file)
    settings["POSTGRES_PASSWORD"] = password
    with pytest.raises(run_staging_compose.StagingComposeValidationError):
        run_staging_compose.validate_staging_settings(settings)


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker CLI unavailable")
def test_staging_literals_survive_real_compose_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / "staging.env"
    _write_staging_environment(env_file, jwt_secret="synthetic-jwt_+/%=:!key")
    settings = run_staging_compose._parse_env_file(env_file)
    password = "synthetic-Long_Random.123~password"
    settings["POSTGRES_PASSWORD"] = password
    settings["DATABASE_URL"] = (
        "postgresql+psycopg://staging_user:"
        f"{quote(password, safe='')}@postgres:5432/staging_db"
    )
    env_file.write_text(
        "\n".join(f"{key}={value}" for key, value in settings.items()), encoding="utf-8"
    )
    run_staging_compose.validate_staging_settings(settings)
    environment = _staging_environment(env_file)
    document = run_staging_compose.staging_compose_document(
        application_image=environment["VDDAI_APPLICATION_IMAGE"],
        artifacts_path=tmp_path.as_posix(),
        environment_file=env_file,
        fqdn=environment["VDDAI_STAGING_FQDN"],
        settings=settings,
        postgres_image=environment["VDDAI_POSTGRES_IMAGE"],
        redis_image=environment["VDDAI_REDIS_IMAGE"],
        caddy_image=environment["VDDAI_CADDY_IMAGE"],
    )
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "unrelated-project")
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--project-name",
            "vddai-staging",
            "-f",
            "-",
            "config",
            "--format",
            "json",
        ],
        input=json.dumps(document),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, "Synthetic Compose render failed"
    rendered = json.loads(result.stdout)
    assert rendered["name"] == "vddai-staging"
    for service in ("api", "worker"):
        actual = rendered["services"][service]["environment"]
        for key in ("JWT_SECRET_KEY", "POSTGRES_PASSWORD", "DATABASE_URL"):
            assert actual[key] == settings[key]
        migration_config = Config("alembic.ini")
        assert not migration_config.get_main_option("sqlalchemy.url")
        migration_config.set_main_option("sqlalchemy.url", actual["DATABASE_URL"])
        assert (
            migration_config.get_main_option("sqlalchemy.url")
            == settings["DATABASE_URL"]
        )
        _, connection = PGDialect_psycopg().create_connect_args(
            make_url(actual["DATABASE_URL"])
        )
        assert connection["host"] == "postgres"
        assert connection["port"] == 5432
        assert connection["password"] == password
        assert connection["dbname"] == "staging_db"
    assert (
        rendered["services"]["postgres"]["environment"]["POSTGRES_PASSWORD"] == password
    )


@pytest.mark.parametrize(
    "password",
    [
        "synthetic:p@ss",
        "synthetic%40pass",
        "synthetic/pass",
        "synthetic+pass",
        "synthetic?pass",
        "synthetic=pass",
    ],
)
def test_staging_rejects_passwords_incompatible_with_migration_startup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, password: str
) -> None:
    env_file = tmp_path / "staging.env"
    _write_staging_environment(env_file)
    settings = run_staging_compose._parse_env_file(env_file)
    settings["POSTGRES_PASSWORD"] = password
    settings["DATABASE_URL"] = (
        "postgresql+psycopg://staging_user:"
        f"{quote(password, safe='')}@postgres:5432/staging_db"
    )
    env_file.write_text(
        "\n".join(f"{key}={value}" for key, value in settings.items()), encoding="utf-8"
    )
    monkeypatch.setattr(
        run_staging_compose,
        "staging_env_file_from_environment",
        lambda _environ: env_file,
    )

    def fail_if_called(*args: object, **kwargs: object) -> None:
        pytest.fail("Unsupported migration credentials must not reach Compose")

    monkeypatch.setattr(run_staging_compose.subprocess, "run", fail_if_called)
    with pytest.raises(run_staging_compose.StagingComposeValidationError):
        run_staging_compose.run_staging_compose(
            ["up", "-d"], environ=_staging_environment(env_file)
        )
