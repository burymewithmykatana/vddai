"""Add database-backed prediction admission guardrails.

Revision ID: 20260821_04
Revises: 20260820_03
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260821_04"
down_revision: str | None = "20260820_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create only internal admission state without rewriting predictions."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "users" not in tables or "predictions" not in tables:
        return

    if "prediction_request_rate_windows" not in tables:
        op.create_table(
            "prediction_request_rate_windows",
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("window_started_at", sa.DateTime(), nullable=False),
            sa.Column("request_count", sa.Integer(), nullable=False),
            sa.CheckConstraint(
                "request_count >= 1",
                name="ck_prediction_request_rate_windows_positive_count",
            ),
        )

    if "prediction_admission_control" not in tables:
        control_table = op.create_table(
            "prediction_admission_control",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.CheckConstraint(
                "id = 1",
                name="ck_prediction_admission_control_singleton",
            ),
        )
        op.bulk_insert(control_table, [{"id": 1}])


def downgrade() -> None:
    """Remove only ephemeral W7D3 admission state."""
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "prediction_request_rate_windows" in tables:
        op.drop_table("prediction_request_rate_windows")
    if "prediction_admission_control" in tables:
        op.drop_table("prediction_admission_control")
