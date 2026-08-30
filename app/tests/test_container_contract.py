from pathlib import Path

from scripts import run_immutable_compose

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_production_dockerfile_builds_a_minimal_runtime_stage() -> None:
    dockerfile = (REPOSITORY_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM ${PYTHON_IMAGE} AS builder" in dockerfile
    assert "FROM ${PYTHON_IMAGE} AS runtime" in dockerfile
    assert "python:3.14.3@sha256:" in dockerfile
    assert "COPY --from=builder /opt/venv /opt/venv" in dockerfile
    assert "COPY app ./app" in dockerfile
    assert "COPY ml ./ml" in dockerfile
    assert "COPY alembic ./alembic" in dockerfile
    assert "COPY alembic.ini ./" in dockerfile
    assert "COPY . ." not in dockerfile
    assert "org.opencontainers.image.revision" in dockerfile


def test_docker_context_excludes_development_and_runtime_state() -> None:
    ignored = set(
        (REPOSITORY_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    )

    assert {"app/tests", "docs", "scripts", "artifacts", "uploads"} <= ignored


def test_immutable_compose_uses_one_image_without_source_substitution() -> None:
    assert not (REPOSITORY_ROOT / "docker-compose.immutable.yaml").exists()
    image_reference = "ghcr.io/burymewithmykatana/vddai@sha256:" + "a" * 64
    artifacts_path = "D:/runtime-artifacts"
    compose = run_immutable_compose.immutable_compose_document(
        image_reference,
        artifacts_path,
    )
    services = compose["services"]
    api = services["api"]
    worker = services["worker"]

    assert api["image"] == worker["image"]
    assert api["image"] == image_reference
    assert "build" not in api
    assert "build" not in worker
    assert api["command"] == (
        'sh -c "alembic upgrade head && exec uvicorn app.main:app --host '
        '0.0.0.0 --port 8000"'
    )
    assert worker["command"] == ["python", "-m", "app.workers.prediction_worker"]
    for service in (api, worker):
        volumes = service["volumes"]
        assert "vddai_uploads:/app/uploads" in volumes
        assert f"{artifacts_path}:/app/artifacts:ro" in volumes
        assert all(".:/app" not in volume for volume in volumes)
