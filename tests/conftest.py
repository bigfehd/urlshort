"""Pytest configuration and fixtures."""
import asyncio
from typing import AsyncGenerator

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.cache import RedisCache
from app.database import Base, get_db_session
from app.main import create_app
from config import get_settings

settings = get_settings()


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests.
    
    Yields:
        Event loop
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def test_db_engine():
    """Create test database engine.
    
    Yields:
        Async SQLAlchemy engine
    """
    # Use in-memory SQLite for tests
    test_db_url = "sqlite+aiosqlite:///:memory:"
    engine = create_async_engine(test_db_url, future=True)

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def test_db_session(test_db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session.
    
    Args:
        test_db_engine: Test database engine
        
    Yields:
        Async SQLAlchemy session
    """
    async_session_maker = sessionmaker(
        test_db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        yield session


@pytest.fixture
async def mock_redis_cache() -> AsyncGenerator[RedisCache, None]:
    """Create mock Redis cache for tests.
    
    Yields:
        Mock RedisCache instance
    """
    cache = RedisCache()
    # Initialize cache dict for mock implementation
    cache._mock_cache = {}

    # Mock the methods to use in-memory dict
    async def mock_get(key: str) -> str | None:
        return cache._mock_cache.get(key)

    async def mock_set(key: str, value, ttl=None) -> bool:
        cache._mock_cache[key] = value
        return True

    async def mock_delete(key: str) -> bool:
        if key in cache._mock_cache:
            del cache._mock_cache[key]
        return True

    async def mock_flush() -> bool:
        cache._mock_cache.clear()
        return True

    async def mock_is_connected() -> bool:
        return True

    async def mock_connect() -> None:
        cache._mock_cache = {}

    async def mock_disconnect() -> None:
        cache._mock_cache.clear()

    cache.get = mock_get
    cache.set = mock_set
    cache.delete = mock_delete
    cache.flush = mock_flush
    cache.is_connected = mock_is_connected
    cache.connect = mock_connect
    cache.disconnect = mock_disconnect

    yield cache


@pytest.fixture
async def client(test_db_session, mock_redis_cache):
    """Create FastAPI test client.
    
    Args:
        test_db_session: Test database session
        mock_redis_cache: Mock Redis cache
        
    Yields:
        AsyncClient for testing
    """
    app = create_app()

    # Override dependencies
    async def override_get_db():
        yield test_db_session

    app.dependency_overrides[get_db_session] = override_get_db

    # Override cache
    from app.cache import cache as real_cache

    original_connect = real_cache.connect
    original_disconnect = real_cache.disconnect

    real_cache.connect = mock_redis_cache.connect
    real_cache.disconnect = mock_redis_cache.disconnect
    real_cache.get = mock_redis_cache.get
    real_cache.set = mock_redis_cache.set
    real_cache.delete = mock_redis_cache.delete
    real_cache.flush = mock_redis_cache.flush
    real_cache.is_connected = mock_redis_cache.is_connected
    real_cache._mock_cache = mock_redis_cache._mock_cache

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

    # Restore original methods
    real_cache.connect = original_connect
    real_cache.disconnect = original_disconnect
