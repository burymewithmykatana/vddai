"""Persist Week 5 anomaly results and frozen package lineage.

Revision ID: 20260801_01
Revises: None
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260801_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade an existing pre-Alembic database without touching fresh DBs."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "predictions" not in inspector.get_table_names():
        return

    columns = {
        column["name"]: column for column in inspector.get_columns("predictions")
    }
    with op.batch_alter_table("predictions") as batch_op:
        if "anomaly_score" not in columns:
            batch_op.add_column(sa.Column("anomaly_score", sa.Float(), nullable=True))
        if "model_lineage" not in columns:
            batch_op.add_column(sa.Column("model_lineage", sa.JSON(), nullable=True))
        batch_op.alter_column(
            "threshold",
            existing_type=sa.Float(),
            nullable=True,
            server_default=None,
        )
        batch_op.alter_column(
            "model_version",
            existing_type=sa.String(length=100),
            nullable=True,
            server_default=None,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "predictions" not in inspector.get_table_names():
        return

    columns = {
        column["name"]: column for column in inspector.get_columns("predictions")
    }
    op.execute(
        sa.text("UPDATE predictions SET threshold = 0.75 WHERE threshold IS NULL")
    )
    op.execute(
        sa.text(
            "UPDATE predictions SET model_version = 'mock-v0' "
            "WHERE model_version IS NULL"
        )
    )
    with op.batch_alter_table("predictions") as batch_op:
        if "model_lineage" in columns:
            batch_op.drop_column("model_lineage")
        if "anomaly_score" in columns:
            batch_op.drop_column("anomaly_score")
        batch_op.alter_column(
            "threshold",
            existing_type=sa.Float(),
            nullable=False,
            server_default="0.75",
        )
        batch_op.alter_column(
            "model_version",
            existing_type=sa.String(length=100),
            nullable=False,
            server_default="mock-v0",
        )
