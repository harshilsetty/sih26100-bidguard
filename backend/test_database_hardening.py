"""Tests for Pre-Deployment Database Hardening & Safety.

SIH26100 — Pre-Deployment Verification:
1. PostgreSQL is the default runtime database.
2. ALLOW_SQLITE_FALLBACK defaults to False.
3. PostgreSQL failure with fallback disabled raises RuntimeError.
4. Explicit ALLOW_SQLITE_FALLBACK=True permits SQLite fallback.
5. Health endpoint identifies PostgreSQL and SQLite fallback correctly.
6. Mock Data Explorer endpoints are 100% read-only.
"""

import asyncio
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.core import database as db_module
from app.api.v1.mock_sources import router as mock_sources_router
from app.api.v1.health import health_check
from app.schemas.health import HealthResponse


def test_postgresql_is_default_runtime():
    """1. Verify PostgreSQL is the default runtime database configuration."""
    assert settings.DATABASE_URL.startswith("postgresql"), (
        f"Expected DATABASE_URL to start with 'postgresql', got: {settings.DATABASE_URL}"
    )
    assert settings.SYNC_DATABASE_URL.startswith("postgresql"), (
        f"Expected SYNC_DATABASE_URL to start with 'postgresql', got: {settings.SYNC_DATABASE_URL}"
    )
    assert "postgres" in settings.DATABASE_URL.lower()


def test_allow_sqlite_fallback_defaults_to_false():
    """2. Verify ALLOW_SQLITE_FALLBACK defaults to False for deployment safety."""
    assert hasattr(settings, "ALLOW_SQLITE_FALLBACK"), "ALLOW_SQLITE_FALLBACK setting missing from config"
    assert settings.ALLOW_SQLITE_FALLBACK is False, (
        f"Expected ALLOW_SQLITE_FALLBACK to be False by default, got: {settings.ALLOW_SQLITE_FALLBACK}"
    )


def test_postgresql_failure_with_fallback_disabled_raises_error():
    """3. Verify PostgreSQL failure with ALLOW_SQLITE_FALLBACK=False raises a clear RuntimeError."""
    async def _run():
        unreachable_url = "postgresql+asyncpg://postgres:wrong@127.0.0.1:59999/nonexistent_db"
        test_engine = create_async_engine(unreachable_url)

        with patch.object(settings, "ALLOW_SQLITE_FALLBACK", False):
            with patch.object(db_module, "engine", test_engine):
                with patch.object(settings, "DATABASE_URL", unreachable_url):
                    with pytest.raises(RuntimeError) as exc_info:
                        await db_module.init_db()

                    err_msg = str(exc_info.value)
                    assert "PostgreSQL is unavailable" in err_msg or "Database initialization failed" in err_msg
                    assert "ALLOW_SQLITE_FALLBACK=False" in err_msg

    asyncio.run(_run())


def test_explicit_fallback_true_permits_sqlite_fallback():
    """4. Verify explicit ALLOW_SQLITE_FALLBACK=True permits local SQLite fallback."""
    async def _run():
        unreachable_url = "postgresql+asyncpg://postgres:wrong@127.0.0.1:59999/nonexistent_db"
        test_engine = create_async_engine(unreachable_url)

        original_engine = db_module.engine
        original_session_local = db_module.AsyncSessionLocal

        try:
            with patch.object(settings, "ALLOW_SQLITE_FALLBACK", True):
                with patch.object(db_module, "engine", test_engine):
                    with patch.object(settings, "DATABASE_URL", unreachable_url):
                        # Should NOT raise RuntimeError; should fallback to SQLite
                        await db_module.init_db()
                        assert "sqlite" in str(db_module.engine.url).lower()
        finally:
            db_module.engine = original_engine
            db_module.AsyncSessionLocal = original_session_local

    asyncio.run(_run())


def test_health_endpoint_identifies_postgresql_correctly():
    """5. Verify health endpoint identifies PostgreSQL dialect as healthy/postgresql."""
    async def _run():
        mock_db = AsyncMock()
        mock_bind = MagicMock()
        mock_bind.dialect.name = "postgresql"
        mock_db.bind = mock_bind

        mock_scalar = MagicMock()
        mock_scalar.scalar.return_value = 1
        mock_ext = MagicMock()
        mock_ext.first.return_value = ("vector", "0.5.1")

        mock_db.execute.side_effect = [mock_scalar, mock_ext]

        resp = await health_check(db=mock_db)

        assert isinstance(resp, HealthResponse)
        assert resp.database == "postgresql"
        assert resp.status == "healthy"
        assert resp.details.get("database_engine") == "postgresql"
        assert resp.details.get("database_status") == "HEALTHY"

    asyncio.run(_run())


def test_health_endpoint_identifies_sqlite_fallback_as_degraded():
    """5b. Verify health endpoint identifies SQLite fallback as degraded/sqlite_fallback."""
    async def _run():
        mock_db = AsyncMock()
        mock_bind = MagicMock()
        mock_bind.dialect.name = "sqlite"
        mock_db.bind = mock_bind

        mock_scalar = MagicMock()
        mock_scalar.scalar.return_value = 1
        mock_db.execute.return_value = mock_scalar

        resp = await health_check(db=mock_db)

        assert isinstance(resp, HealthResponse)
        assert resp.database == "sqlite_fallback"
        assert resp.status == "degraded"
        assert resp.details.get("database_engine") == "sqlite_fallback"

    asyncio.run(_run())


def test_mock_explorer_remains_read_only():
    """6. Verify all Mock Data Explorer endpoints are strictly HTTP GET (read-only)."""
    routes = mock_sources_router.routes
    assert len(routes) > 0, "No routes found in mock_sources router"

    for route in routes:
        methods = getattr(route, "methods", set())
        # Strip HEAD which FastAPI automatically adds to GET endpoints
        non_safe_methods = {m for m in methods if m not in {"GET", "HEAD"}}
        assert len(non_safe_methods) == 0, (
            f"Found forbidden non-read-only method(s) {non_safe_methods} on endpoint '{route.path}'"
        )
        assert "GET" in methods, f"Route '{route.path}' does not support GET"
