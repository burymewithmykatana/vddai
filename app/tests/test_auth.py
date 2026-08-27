from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.routes import auth as auth_route
from app.models.user import User
from app.schemas.user import UserCreate

pytestmark = pytest.mark.w7_production_gate


def _commit_integrity_error() -> IntegrityError:
    return IntegrityError(
        "INSERT INTO users",
        {},
        RuntimeError("simulated unique conflict"),
    )


def test_registration_translates_commit_time_duplicate_to_409_and_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = MagicMock(spec=Session)
    db.scalar.side_effect = [
        None,
        User(email="race@example.com", hashed_password="existing"),
    ]
    db.commit.side_effect = _commit_integrity_error()
    monkeypatch.setattr(auth_route, "hash_password", lambda password: "hashed")

    with pytest.raises(HTTPException) as exc_info:
        auth_route.register_user(
            UserCreate(email="race@example.com", password="password123"),
            db,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "A user with this email already exists."
    db.rollback.assert_called_once_with()


def test_registration_does_not_mask_unrelated_integrity_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = MagicMock(spec=Session)
    db.scalar.side_effect = [None, None]
    integrity_error = _commit_integrity_error()
    db.commit.side_effect = integrity_error
    monkeypatch.setattr(auth_route, "hash_password", lambda password: "hashed")

    with pytest.raises(IntegrityError) as exc_info:
        auth_route.register_user(
            UserCreate(email="new@example.com", password="password123"),
            db,
        )

    assert exc_info.value is integrity_error
    db.rollback.assert_called_once_with()
