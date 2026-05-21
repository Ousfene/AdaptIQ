import time
import uuid

import pytest
from fastapi import HTTPException
from jose import jwt

from config import JWT_ALGORITHM, JWT_SECRET_KEY
from routers.auth import (
    _create_access_token,
    _hash_password,
    _verify_password,
    get_current_user,
)


def test_password_hash_and_verify_roundtrip() -> None:
    password = "TestPass123!"
    password_hash = _hash_password(password)

    assert password_hash != password
    assert _verify_password(password, password_hash) is True
    assert _verify_password("wrong-password", password_hash) is False


def test_create_access_token_contains_expected_claims() -> None:
    user_id = str(uuid.uuid4())
    token = _create_access_token(user_id)

    payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])

    assert payload.get("sub") == user_id
    assert isinstance(payload.get("iat"), int)
    assert isinstance(payload.get("exp"), int)
    assert payload["exp"] > payload["iat"]

    jti = payload.get("jti")
    assert isinstance(jti, str)
    uuid.UUID(jti)


@pytest.mark.asyncio
async def test_get_current_user_rejects_missing_bearer_token() -> None:
    class _Db:
        async def get(self, *_args, **_kwargs):
            raise AssertionError("db.get must not be called")

    with pytest.raises(HTTPException) as exc:
        await get_current_user(request=None, authorization=None, db=_Db())

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_rejects_non_uuid_sub() -> None:
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": "not-a-uuid",
            "iat": now,
            "exp": now + 60,
            "jti": str(uuid.uuid4()),
        },
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )

    class _Db:
        async def get(self, *_args, **_kwargs):
            raise AssertionError("db.get must not be called")

    with pytest.raises(HTTPException) as exc:
        await get_current_user(request=None, authorization=f"Bearer {token}", db=_Db())

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid token payload"
