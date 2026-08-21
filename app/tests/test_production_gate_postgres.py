import os
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine, make_url

POSTGRES_TEST_URL = os.environ.get("VDDAI_TEST_POSTGRES_DATABASE_URL")
ALEMBIC_HEAD = "20260821_04"

pytestmark = [
    pytest.mark.w7_production_gate,
    pytest.mark.postgres_integration,
    pytest.mark.skipif(
        not POSTGRES_TEST_URL,
        reason="VDDAI_TEST_POSTGRES_DATABASE_URL is not configured.",
    ),
]


def _schema_database_url(database_url: str, *, schema_name: str) -> str:
    url = make_url(database_url)
    query = dict(url.query)
    query["options"] = f"-csearch_path={schema_name}"
    return url.set(query=query).render_as_string(hide_password=False)


def _alembic_config(database_url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def _seed_legacy_schema(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE users ("
                "id INTEGER PRIMARY KEY, "
                "email VARCHAR(255) NOT NULL UNIQUE)"
            )
        )
        connection.execute(
            sa.text(
                "CREATE TABLE predictions ("
                "id INTEGER PRIMARY KEY, "
                "user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                "status VARCHAR(50) NOT NULL, "
                "threshold DOUBLE PRECISION NOT NULL DEFAULT 0.75, "
                "model_version VARCHAR(100) NOT NULL DEFAULT 'mock-v0', "
                "error_message TEXT, "
                "created_at TIMESTAMP WITHOUT TIME ZONE, "
                "completed_at TIMESTAMP WITHOUT TIME ZONE)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO users (id, email) " "VALUES (1, 'w7d4-legacy@example.com')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO predictions "
                "(id, user_id, status, threshold, model_version, error_message, "
                "created_at) VALUES "
                "(7, 1, 'processing', 0.9, 'legacy-v1', "
                "'legacy diagnostic', '2026-08-01 12:00:00')"
            )
        )


def _prediction_snapshot(engine: Engine) -> dict[str, object]:
    with engine.connect() as connection:
        return dict(
            connection.execute(
                sa.text(
                    "SELECT id, user_id, status, threshold, model_version, "
                    "error_message FROM predictions WHERE id = 7"
                )
            )
            .mappings()
            .one()
        )


def _current_revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return connection.scalar(sa.text("SELECT version_num FROM alembic_version"))


def test_postgres_migration_upgrade_downgrade_reupgrade_preserves_legacy_data() -> None:
    assert POSTGRES_TEST_URL is not None
    schema_name = f"vddai_w7d4_{uuid4().hex}"
    administration_engine = sa.create_engine(POSTGRES_TEST_URL)
    schema_engine: Engine | None = None
    schema_created = False

    try:
        with administration_engine.begin() as connection:
            server_version_num = int(
                connection.scalar(sa.text("SHOW server_version_num"))
            )
            assert server_version_num // 10000 == 16
            connection.execute(sa.text(f'CREATE SCHEMA "{schema_name}"'))
            schema_created = True

        schema_database_url = _schema_database_url(
            POSTGRES_TEST_URL,
            schema_name=schema_name,
        )
        schema_engine = sa.create_engine(schema_database_url)
        migration_config = _alembic_config(schema_database_url)
        _seed_legacy_schema(schema_engine)

        command.upgrade(migration_config, "head")

        upgraded_tables = set(sa.inspect(schema_engine).get_table_names())
        upgraded_columns = {
            column["name"]
            for column in sa.inspect(schema_engine).get_columns("predictions")
        }
        with schema_engine.connect() as connection:
            admission_control_id = connection.scalar(
                sa.text("SELECT id FROM prediction_admission_control")
            )

        assert _current_revision(schema_engine) == ALEMBIC_HEAD
        assert {
            "prediction_request_rate_windows",
            "prediction_admission_control",
        }.issubset(upgraded_tables)
        assert {
            "anomaly_score",
            "model_lineage",
            "processing_started_at",
            "attempt_count",
            "lease_expires_at",
            "next_attempt_at",
        }.issubset(upgraded_columns)
        assert admission_control_id == 1
        assert _prediction_snapshot(schema_engine) == {
            "id": 7,
            "user_id": 1,
            "status": "processing",
            "threshold": 0.9,
            "model_version": "legacy-v1",
            "error_message": "legacy diagnostic",
        }

        command.downgrade(migration_config, "base")

        downgraded_tables = set(sa.inspect(schema_engine).get_table_names())
        downgraded_columns = {
            column["name"]
            for column in sa.inspect(schema_engine).get_columns("predictions")
        }
        assert _current_revision(schema_engine) is None
        assert "prediction_request_rate_windows" not in downgraded_tables
        assert "prediction_admission_control" not in downgraded_tables
        assert {
            "anomaly_score",
            "model_lineage",
            "processing_started_at",
            "attempt_count",
            "lease_expires_at",
            "next_attempt_at",
        }.isdisjoint(downgraded_columns)
        assert _prediction_snapshot(schema_engine) == {
            "id": 7,
            "user_id": 1,
            "status": "processing",
            "threshold": 0.9,
            "model_version": "legacy-v1",
            "error_message": "legacy diagnostic",
        }

        command.upgrade(migration_config, "head")

        reupgraded_tables = set(sa.inspect(schema_engine).get_table_names())
        reupgraded_columns = {
            column["name"]
            for column in sa.inspect(schema_engine).get_columns("predictions")
        }
        assert _current_revision(schema_engine) == ALEMBIC_HEAD
        assert {
            "prediction_request_rate_windows",
            "prediction_admission_control",
        }.issubset(reupgraded_tables)
        assert {
            "anomaly_score",
            "model_lineage",
            "processing_started_at",
            "attempt_count",
            "lease_expires_at",
            "next_attempt_at",
        }.issubset(reupgraded_columns)
        assert _prediction_snapshot(schema_engine) == {
            "id": 7,
            "user_id": 1,
            "status": "processing",
            "threshold": 0.9,
            "model_version": "legacy-v1",
            "error_message": "legacy diagnostic",
        }
    finally:
        if schema_engine is not None:
            schema_engine.dispose()
        if schema_created:
            with administration_engine.begin() as connection:
                connection.execute(sa.text(f'DROP SCHEMA "{schema_name}" CASCADE'))
        administration_engine.dispose()
