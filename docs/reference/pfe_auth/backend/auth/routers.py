"""Legacy import path for the auth router. Prefer routers.auth."""

from routers.auth import router

__all__ = ["router"]