from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    # sqlalchemy finds out each model inhereting this is a table
    pass
