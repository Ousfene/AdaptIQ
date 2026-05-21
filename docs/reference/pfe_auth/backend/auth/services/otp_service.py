import secrets
import string
import hashlib
import hmac
from typing import Optional

from fastapi import HTTPException, status

# All OTP tuneable constants come from config.py so they can be adjusted
# in one place (or via environment variables) without touching this file.
from config import OTP_LENGTH, OTP_EXPIRE_SECONDS, OTP_MAX_ATTEMPTS

OTP_PURPOSE_EMAIL_VERIFY = "email_verify"
OTP_PURPOSE_LOGIN_2FA = "login_2fa"
OTP_PURPOSE_PASSWORD_RESET = "password_reset"
VALID_PURPOSES = {OTP_PURPOSE_EMAIL_VERIFY, OTP_PURPOSE_LOGIN_2FA, OTP_PURPOSE_PASSWORD_RESET}


def _otp_key(email: str, purpose: str) -> str:
    return f"otp:{purpose}:{email.lower()}"


def _otp_attempts_key(email: str, purpose: str) -> str:
    return f"otp_attempts:{purpose}:{email.lower()}"


def generate_otp_code(length: Optional[int] = None) -> str:
    n = length or OTP_LENGTH
    return "".join(secrets.choice(string.digits) for _ in range(n))


def _hash_otp(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


async def create_otp(redis, email: str, purpose: str) -> str:
    if purpose not in VALID_PURPOSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP purpose")
    code = generate_otp_code()
    await redis.set(_otp_key(email, purpose), _hash_otp(code), ex=OTP_EXPIRE_SECONDS)
    await redis.set(_otp_attempts_key(email, purpose), "0", ex=OTP_EXPIRE_SECONDS)
    return code


async def verify_otp(redis, email: str, purpose: str, code: str) -> bool:
    if purpose not in VALID_PURPOSES:
        return False
    key = _otp_key(email, purpose)
    attempts_key = _otp_attempts_key(email, purpose)

    attempts_raw = await redis.get(attempts_key)
    attempts = int(attempts_raw) if attempts_raw else 0
    if attempts >= OTP_MAX_ATTEMPTS:
        await redis.delete(key)
        await redis.delete(attempts_key)
        return False

    stored_hash = await redis.get(key)
    if stored_hash is None:
        return False

    code_hash = _hash_otp(code)
    if not hmac.compare_digest(str(stored_hash), code_hash):
        await redis.incr(attempts_key)
        return False

    await redis.delete(key)
    await redis.delete(attempts_key)
    return True
