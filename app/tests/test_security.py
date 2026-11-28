from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe

import jwt
import pytest

from app.core.config import settings
from app.core.security import ALGORITHM, create_access_token, decode_access_token


@pytest.fixture(autouse=True)
def signing_key(monkeypatch) -> str:
    key = token_urlsafe(64)
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", key)
    return key


def test_access_tokens_remain_hs256_only() -> None:
    token = create_access_token(subject=7)

    assert ALGORITHM == "HS256"
    assert jwt.get_unverified_header(token)["alg"] == "HS256"
    claims = decode_access_token(token)
    assert claims is not None
    assert claims["sub"] == "7"
    assert claims["exp"] > datetime.now(timezone.utc).timestamp()


@pytest.mark.parametrize("age", [timedelta(0), timedelta(seconds=-1)])
def test_access_token_at_or_after_expiration_is_rejected(age) -> None:
    token = create_access_token(subject=7, expires_delta=age)

    assert decode_access_token(token) is None


def test_access_token_requires_the_configured_signature_and_algorithm(
    signing_key,
) -> None:
    claims = {"sub": "7", "exp": datetime.now(timezone.utc) + timedelta(minutes=1)}
    different_key = jwt.encode(claims, token_urlsafe(64), algorithm="HS256")
    different_algorithm = jwt.encode(claims, signing_key, algorithm="HS384")

    assert decode_access_token(different_key) is None
    assert decode_access_token(different_algorithm) is None


@pytest.mark.parametrize("expiration", [None, [], {}, "not-a-number"])
def test_invalid_expiration_claim_fails_closed(signing_key, expiration) -> None:
    token = jwt.encode({"sub": "7", "exp": expiration}, signing_key, algorithm="HS256")

    assert decode_access_token(token) is None


def test_malformed_access_token_fails_closed() -> None:
    assert decode_access_token("invalid-token") is None
