"""Add bounded prediction retry and lease metadata.

Revision ID: 20260820_03
Revises: 20260803_02
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260820_03"
down_revision: str | None = "20260803_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add internal retry metadata without rewriting prediction history."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "predictions" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("predictions")}
    with op.batch_alter_table("predictions") as batch_op:
        if "attempt_count" not in columns:
            batch_op.add_column(
                sa.Column(
                    "attempt_count",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                )
            )
        if "lease_expires_at" not in columns:
            batch_op.add_column(
                sa.Column("lease_expires_at", sa.DateTime(), nullable=True)
            )
        if "next_attempt_at" not in columns:
            batch_op.add_column(
                sa.Column("next_attempt_at", sa.DateTime(), nullable=True)
            )


def downgrade() -> None:
    """Remove only retry metadata introduced by this revision."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "predictions" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("predictions")}
    with op.batch_alter_table("predictions") as batch_op:
        if "next_attempt_at" in columns:
            batch_op.drop_column("next_attempt_at")
        if "lease_expires_at" in columns:
            batch_op.drop_column("lease_expires_at")
        if "attempt_count" in columns:
            batch_op.drop_column("attempt_count")
