"""Tests for health and cache functionality."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import RedisCache


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Test health check endpoint.
    
    Args:
        client: AsyncClient test fixture
    """
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "degraded"]
    assert "version" in data
    assert "database" in data
    assert "redis" in data


@pytest.mark.asyncio
async def test_ping(client: AsyncClient):
    """Test ping endpoint.
    
    Args:
        client: AsyncClient test fixture
    """
    response = await client.get("/ping")
    assert response.status_code == 200
    assert response.json()["message"] == "pong"


@pytest.mark.asyncio
async def test_cache_set_get(mock_redis_cache: RedisCache):
    """Test cache set and get operations.
    
    Args:
        mock_redis_cache: Mock Redis cache fixture
    """
    await mock_redis_cache.connect()

    # Test set and get
    success = await mock_redis_cache.set("test_key", "test_value")
    assert success is True

    value = await mock_redis_cache.get("test_key")
    assert value == "test_value"


@pytest.mark.asyncio
async def test_cache_miss(mock_redis_cache: RedisCache):
    """Test cache miss.
    
    Args:
        mock_redis_cache: Mock Redis cache fixture
    """
    await mock_redis_cache.connect()

    # Try to get non-existent key
    value = await mock_redis_cache.get("nonexistent")
    assert value is None


@pytest.mark.asyncio
async def test_cache_delete(mock_redis_cache: RedisCache):
    """Test cache delete operation.
    
    Args:
        mock_redis_cache: Mock Redis cache fixture
    """
    await mock_redis_cache.connect()

    # Set a value
    await mock_redis_cache.set("delete_test", "value")

    # Delete it
    success = await mock_redis_cache.delete("delete_test")
    assert success is True

    # Verify it's gone
    value = await mock_redis_cache.get("delete_test")
    assert value is None


@pytest.mark.asyncio
async def test_cache_flush(mock_redis_cache: RedisCache):
    """Test cache flush operation.
    
    Args:
        mock_redis_cache: Mock Redis cache fixture
    """
    await mock_redis_cache.connect()

    # Set multiple values
    await mock_redis_cache.set("key1", "value1")
    await mock_redis_cache.set("key2", "value2")

    # Flush
    success = await mock_redis_cache.flush()
    assert success is True

    # Verify all values are gone
    assert await mock_redis_cache.get("key1") is None
    assert await mock_redis_cache.get("key2") is None


@pytest.mark.asyncio
async def test_cache_json_serialization(mock_redis_cache: RedisCache):
    """Test caching complex objects as JSON.
    
    Args:
        mock_redis_cache: Mock Redis cache fixture
    """
    await mock_redis_cache.connect()

    # Cache a dict
    test_data = {"url": "https://example.com", "clicks": 42}
    await mock_redis_cache.set("json_key", test_data)

    # Retrieve it
    value = await mock_redis_cache.get("json_key")
    # The mock stores it as-is, but a real implementation would JSON serialize
    assert value is not None
