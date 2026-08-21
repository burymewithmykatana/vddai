from app.db.base import Base
from app.db.session import engine
from sqlalchemy.exc import IntegrityError

# Import models so SQLAlchemy registers them before create_all
from app.models import (  # noqa: F401
    Prediction,
    PredictionAdmissionControl,
    PredictionRequestRateWindow,
    User,
)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    try:
        with engine.begin() as connection:
            exists = connection.execute(
                PredictionAdmissionControl.__table__.select().where(
                    PredictionAdmissionControl.id == 1
                )
            ).first()
            if exists is None:
                connection.execute(
                    PredictionAdmissionControl.__table__.insert().values(id=1)
                )
    except IntegrityError:
        # Another process may seed the singleton between the read and insert.
        pass
