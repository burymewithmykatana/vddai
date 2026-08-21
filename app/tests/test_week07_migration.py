from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config


def test_week07_migration_preserves_predictions_and_downgrades(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "week07.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = sa.create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(sa.text("""
                CREATE TABLE predictions (
                    id INTEGER PRIMARY KEY,
                    status VARCHAR(50) NOT NULL,
                    threshold FLOAT NOT NULL DEFAULT 0.75,
                    model_version VARCHAR(100) NOT NULL DEFAULT 'mock-v0',
                    error_message TEXT,
                    created_at DATETIME,
                    completed_at DATETIME
                )
                """))
        connection.execute(
            sa.text(
                "INSERT INTO predictions "
                "(id, status, threshold, model_version, error_message, created_at) "
                "VALUES (1, 'processing', 0.9, 'legacy-v1', 'legacy diagnostic', "
                "'2026-08-01 12:00:00')"
            )
        )
    engine.dispose()

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")

    migrated_engine = sa.create_engine(database_url)
    columns = {
        column["name"]: column
        for column in sa.inspect(migrated_engine).get_columns("predictions")
    }
    with migrated_engine.connect() as connection:
        migrated = (
            connection.execute(
                sa.text(
                    "SELECT id, status, threshold, model_version, error_message, "
                    "attempt_count, lease_expires_at, next_attempt_at "
                    "FROM predictions WHERE id = 1"
                )
            )
            .mappings()
            .one()
        )
    migrated_engine.dispose()

    assert columns["attempt_count"]["nullable"] is False
    assert columns["lease_expires_at"]["nullable"] is True
    assert columns["next_attempt_at"]["nullable"] is True
    assert dict(migrated) == {
        "id": 1,
        "status": "processing",
        "threshold": 0.9,
        "model_version": "legacy-v1",
        "error_message": "legacy diagnostic",
        "attempt_count": 0,
        "lease_expires_at": None,
        "next_attempt_at": None,
    }

    command.downgrade(config, "20260803_02")
    downgraded_engine = sa.create_engine(database_url)
    downgraded_columns = {
        column["name"]
        for column in sa.inspect(downgraded_engine).get_columns("predictions")
    }
    with downgraded_engine.connect() as connection:
        preserved = (
            connection.execute(
                sa.text(
                    "SELECT id, status, threshold, model_version, error_message "
                    "FROM predictions WHERE id = 1"
                )
            )
            .mappings()
            .one()
        )
    downgraded_engine.dispose()

    assert "attempt_count" not in downgraded_columns
    assert "lease_expires_at" not in downgraded_columns
    assert "next_attempt_at" not in downgraded_columns
    assert dict(preserved) == {
        "id": 1,
        "status": "processing",
        "threshold": 0.9,
        "model_version": "legacy-v1",
        "error_message": "legacy diagnostic",
    }
