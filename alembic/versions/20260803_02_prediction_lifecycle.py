"""Add the auditable prediction processing timestamp.

Revision ID: 20260803_02
Revises: 20260801_01
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260803_02"
down_revision: str | None = "20260801_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add a nullable timestamp without fabricating legacy lifecycle data."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "predictions" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("predictions")}
    if "processing_started_at" not in columns:
        with op.batch_alter_table("predictions") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "processing_started_at",
                    sa.DateTime(),
                    nullable=True,
                )
            )


def downgrade() -> None:
    """Remove only the lifecycle column introduced by this revision."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "predictions" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("predictions")}
    if "processing_started_at" in columns:
        with op.batch_alter_table("predictions") as batch_op:
            batch_op.drop_column("processing_started_at")
