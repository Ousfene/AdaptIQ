"""Compatibility exports for auth schemas. Prefer importing from schemas.py."""

from schemas import (
    AuthResponse,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    OTPResponse,
    RegisterRequest,
    ResetPasswordRequest,
    UserResponse,
)

__all__ = [
    "AuthResponse",
    "ForgotPasswordRequest",
    "LoginRequest",
    "MessageResponse",
    "OTPResponse",
    "RegisterRequest",
    "ResetPasswordRequest",
    "UserResponse",
]