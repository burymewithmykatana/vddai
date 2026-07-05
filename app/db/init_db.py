from app.db.base import Base
from app.db.session import engine

# Import models so SQLAlchemy registers them before create_all
from app.models import User, Prediction  # noqa: F401


def init_db() -> None:
    Base.metadata.create_all(bind=engine)