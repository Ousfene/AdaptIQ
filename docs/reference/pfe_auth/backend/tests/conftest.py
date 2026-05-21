"""Pytest configuration and fixtures."""
import sys
from pathlib import Path
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

# Add backend directory to Python path so imports work
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from main import app


@pytest.fixture
async def api_client() -> AsyncGenerator[AsyncClient, None]:
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url='http://testserver') as client:
            yield client
