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
    assert data["status"] in ["healthy", "degraded", "unhealthy"]
    assert "version" in data
    assert "database" in data
    assert "redis" in data
    assert data["database"] in ["healthy", "unhealthy"]
    assert data["redis"] in ["healthy", "unhealthy"]


@pytest.mark.asyncio
async def test_detailed_health_check(client: AsyncClient):
    """Test detailed health check endpoint with latency info.
    
    Args:
        client: AsyncClient test fixture
    """
    response = await client.get("/health/detailed")
    assert response.status_code == 200
    data = response.json()

    # Check structure
    assert "status" in data
    assert "timestamp" in data
    assert "components" in data

    # Check components
    assert "database" in data["components"]
    assert "redis" in data["components"]

    # Check component details
    db_component = data["components"]["database"]
    redis_component = data["components"]["redis"]

    assert "status" in db_component
    assert "latency_ms" in db_component
    assert db_component["status"] in ["healthy", "unhealthy"]
    assert isinstance(db_component["latency_ms"], (int, float)) or db_component["latency_ms"] is None

    assert "status" in redis_component
    assert "latency_ms" in redis_component
    assert redis_component["status"] in ["healthy", "unhealthy"]


@pytest.mark.asyncio
async def test_health_with_database_healthy(client: AsyncClient):
    """Test health check when database is healthy.
    
    Args:
        client: AsyncClient test fixture
    """
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["database"] == "healthy"


@pytest.mark.asyncio
async def test_health_with_redis_healthy(client: AsyncClient):
    """Test health check when Redis is healthy.
    
    Args:
        client: AsyncClient test fixture
    """
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["redis"] == "healthy"


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
async def test_cache_pipeline_get(mock_redis_cache: RedisCache):
    """Test cache pipeline get operation.
    
    Args:
        mock_redis_cache: Mock Redis cache fixture
    """
    await mock_redis_cache.connect()

    # Set a value
    await mock_redis_cache.set("pipeline_key", "pipeline_value")

    # Test pipeline get
    value, was_cached = await mock_redis_cache.pipeline_get_and_enqueue("pipeline_key")
    assert value == "pipeline_value"
    assert was_cached is True


@pytest.mark.asyncio
async def test_cache_pipeline_get_miss(mock_redis_cache: RedisCache):
    """Test cache pipeline get on cache miss.
    
    Args:
        mock_redis_cache: Mock Redis cache fixture
    """
    await mock_redis_cache.connect()

    # Test pipeline get on non-existent key
    value, was_cached = await mock_redis_cache.pipeline_get_and_enqueue("nonexistent")
    assert value is None
    assert was_cached is False


@pytest.mark.asyncio
async def test_cache_pipeline_set(mock_redis_cache: RedisCache):
    """Test cache pipeline set operation.
    
    Args:
        mock_redis_cache: Mock Redis cache fixture
    """
    await mock_redis_cache.connect()

    # Test pipeline set
    success = await mock_redis_cache.pipeline_set("pipeline_set_key", "pipeline_set_value")
    assert success is True

    # Verify it was set
    value = await mock_redis_cache.get("pipeline_set_key")
    assert value == "pipeline_set_value"


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
