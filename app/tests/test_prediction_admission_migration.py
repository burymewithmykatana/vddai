from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

pytestmark = pytest.mark.w7_production_gate


def test_prediction_admission_migration_upgrades_and_downgrades(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "prediction-admission.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "20260820_03")

    engine = sa.create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE users ("
                "id INTEGER PRIMARY KEY, email VARCHAR(255) NOT NULL)"
            )
        )
        connection.execute(
            sa.text(
                "CREATE TABLE predictions ("
                "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
                "status VARCHAR(50) NOT NULL)"
            )
        )
        connection.execute(
            sa.text("INSERT INTO users (id, email) VALUES (1, 'legacy@example.com')")
        )
        connection.execute(
            sa.text(
                "INSERT INTO predictions (id, user_id, status) "
                "VALUES (7, 1, 'queued')"
            )
        )
    engine.dispose()

    command.upgrade(config, "head")
    upgraded = sa.create_engine(database_url)
    tables = set(sa.inspect(upgraded).get_table_names())
    with upgraded.connect() as connection:
        control_id = connection.scalar(
            sa.text("SELECT id FROM prediction_admission_control")
        )
        prediction = connection.execute(
            sa.text("SELECT id, user_id, status FROM predictions WHERE id = 7")
        ).one()
    upgraded.dispose()

    assert "prediction_request_rate_windows" in tables
    assert "prediction_admission_control" in tables
    assert control_id == 1
    assert tuple(prediction) == (7, 1, "queued")

    command.downgrade(config, "20260820_03")
    downgraded = sa.create_engine(database_url)
    downgraded_tables = set(sa.inspect(downgraded).get_table_names())
    with downgraded.connect() as connection:
        preserved = connection.execute(
            sa.text("SELECT id, user_id, status FROM predictions WHERE id = 7")
        ).one()
    downgraded.dispose()

    assert "prediction_request_rate_windows" not in downgraded_tables
    assert "prediction_admission_control" not in downgraded_tables
    assert tuple(preserved) == (7, 1, "queued")

    command.upgrade(config, "head")
