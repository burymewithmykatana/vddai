from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config


def test_week05_migration_upgrades_pre_alembic_prediction_table(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "legacy.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = sa.create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(sa.text("""
                CREATE TABLE predictions (
                    id INTEGER PRIMARY KEY,
                    threshold FLOAT NOT NULL DEFAULT 0.75,
                    model_version VARCHAR(100) NOT NULL DEFAULT 'mock-v0'
                )
                """))
    engine.dispose()

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")

    migrated_engine = sa.create_engine(database_url)
    columns = {
        column["name"]: column
        for column in sa.inspect(migrated_engine).get_columns("predictions")
    }
    migrated_engine.dispose()

    assert columns["anomaly_score"]["nullable"] is True
    assert columns["model_lineage"]["nullable"] is True
    assert columns["threshold"]["nullable"] is True
    assert columns["threshold"]["default"] is None
    assert columns["model_version"]["nullable"] is True
    assert columns["model_version"]["default"] is None

    command.downgrade(config, "base")
    downgraded_engine = sa.create_engine(database_url)
    downgraded_columns = {
        column["name"]: column
        for column in sa.inspect(downgraded_engine).get_columns("predictions")
    }
    downgraded_engine.dispose()

    assert "anomaly_score" not in downgraded_columns
    assert "model_lineage" not in downgraded_columns
    assert downgraded_columns["threshold"]["nullable"] is False
    assert downgraded_columns["model_version"]["nullable"] is False
