from jose import jwt

from app.core.security import ALGORITHM, create_access_token, decode_access_token


def test_access_tokens_remain_hs256_only() -> None:
    token = create_access_token(subject="security-test")

    assert ALGORITHM == "HS256"
    assert jwt.get_unverified_header(token)["alg"] == "HS256"
    assert decode_access_token(token) is not None
