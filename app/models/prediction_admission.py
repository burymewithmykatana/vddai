from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PredictionRequestRateWindow(Base):
    __tablename__ = "prediction_request_rate_windows"
    __table_args__ = (
        CheckConstraint(
            "request_count >= 1",
            name="ck_prediction_request_rate_windows_positive_count",
        ),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    window_started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False)


class PredictionAdmissionControl(Base):
    __tablename__ = "prediction_admission_control"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_prediction_admission_control_singleton"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
