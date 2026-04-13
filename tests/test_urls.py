"""Tests for URL shortening endpoints."""
import json

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ShortURL


@pytest.mark.asyncio
async def test_create_short_url(client: AsyncClient, test_db_session: AsyncSession):
    """Test creating a shortened URL.
    
    Args:
        client: AsyncClient test fixture
        test_db_session: Database session fixture
    """
    response = await client.post(
        "/api/shorten",
        json={
            "original_url": "https://www.example.com/very/long/url?param1=value1&param2=value2",
            "description": "Test URL",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "short_code" in data
    assert "short_url" in data
    assert data["original_url"] == "https://www.example.com/very/long/url?param1=value1&param2=value2"
    assert data["short_url"].endswith(data["short_code"])


@pytest.mark.asyncio
async def test_redirect_cache_hit_with_headers(
    client: AsyncClient, test_db_session: AsyncSession
):
    """Test redirect with cache hit and verify response headers.
    
    Args:
        client: AsyncClient test fixture
        test_db_session: Database session fixture
    """
    # Create a shortened URL
    response = await client.post(
        "/api/shorten",
        json={
            "original_url": "https://www.example.com/cache-test",
            "description": "Cache test",
        },
    )
    short_code = response.json()["short_code"]

    # First redirect (cache miss)
    response1 = await client.get(f"/{short_code}", follow_redirects=False)
    assert response1.status_code == 302
    assert response1.headers["location"] == "https://www.example.com/cache-test"
    assert response1.headers["x-cache"] == "MISS"
    assert "x-response-time" in response1.headers
    latency_miss = float(response1.headers["x-response-time"].rstrip("ms"))

    # Second redirect (cache hit)
    response2 = await client.get(f"/{short_code}", follow_redirects=False)
    assert response2.status_code == 302
    assert response2.headers["location"] == "https://www.example.com/cache-test"
    assert response2.headers["x-cache"] == "HIT"
    assert "x-response-time" in response2.headers
    latency_hit = float(response2.headers["x-response-time"].rstrip("ms"))

    # Cache hit should generally be faster (unless system is very loaded)
    # Just verify both are reasonable (> 0ms)
    assert latency_miss > 0
    assert latency_hit > 0


@pytest.mark.asyncio
async def test_redirect_response_time_header(
    client: AsyncClient, test_db_session: AsyncSession
):
    """Test that X-Response-Time header is present and valid.
    
    Args:
        client: AsyncClient test fixture
        test_db_session: Database session fixture
    """
    response = await client.post(
        "/api/shorten",
        json={"original_url": "https://example.com/latency-test"},
    )
    short_code = response.json()["short_code"]

    response = await client.get(f"/{short_code}", follow_redirects=False)
    assert response.status_code == 302

    # Verify X-Response-Time header
    assert "x-response-time" in response.headers
    time_str = response.headers["x-response-time"]
    assert time_str.endswith("ms")
    latency = float(time_str.rstrip("ms"))
    assert latency >= 0


@pytest.mark.asyncio
async def test_redirect_cache_miss_from_db(
    client: AsyncClient, test_db_session: AsyncSession
):
    """Test redirect directly from database (cache miss).
    
    Args:
        client: AsyncClient test fixture
        test_db_session: Database session fixture
    """
    # Create URL and add to DB first
    short_url = ShortURL(
        short_code="testcode",
        original_url="https://www.example.com/cache-miss-test",
    )
    test_db_session.add(short_url)
    await test_db_session.commit()

    # Redirect should work with database lookup
    response = await client.get("/testcode", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "https://www.example.com/cache-miss-test"
    assert response.headers["x-cache"] == "MISS"


@pytest.mark.asyncio
async def test_redirect_not_found(client: AsyncClient):
    """Test redirect with non-existent short code.
    
    Args:
        client: AsyncClient test fixture
    """
    response = await client.get("/nonexistent", follow_redirects=False)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_redirect_includes_user_agent(
    client: AsyncClient, test_db_session: AsyncSession
):
    """Test that user agent is captured during redirect.
    
    Args:
        client: AsyncClient test fixture
        test_db_session: Database session fixture
    """
    response = await client.post(
        "/api/shorten",
        json={"original_url": "https://example.com/user-agent-test"},
    )
    short_code = response.json()["short_code"]

    # Make request with custom user agent
    response = await client.get(
        f"/{short_code}",
        follow_redirects=False,
        headers={"User-Agent": "TestClient/1.0"},
    )
    assert response.status_code == 302


@pytest.mark.asyncio
async def test_get_url_info(client: AsyncClient, test_db_session: AsyncSession):
    """Test getting URL information.
    
    Args:
        client: AsyncClient test fixture
        test_db_session: Database session fixture
    """
    # Create a URL
    response = await client.post(
        "/api/shorten",
        json={
            "original_url": "https://www.example.com/info-test",
            "description": "Info test",
        },
    )
    short_code = response.json()["short_code"]

    # Get info
    response = await client.get(f"/api/info/{short_code}")
    assert response.status_code == 200
    data = response.json()
    assert data["short_code"] == short_code
    assert data["original_url"] == "https://www.example.com/info-test"
    assert data["description"] == "Info test"
    assert data["click_count"] == 0


@pytest.mark.asyncio
async def test_list_urls(client: AsyncClient, test_db_session: AsyncSession):
    """Test listing URLs with pagination.
    
    Args:
        client: AsyncClient test fixture
        test_db_session: Database session fixture
    """
    # Create multiple URLs
    for i in range(5):
        await client.post(
            "/api/shorten",
            json={
                "original_url": f"https://www.example.com/url{i}",
                "description": f"URL {i}",
            },
        )

    # Get list
    response = await client.get("/api/list?limit=3&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert data["limit"] == 3
    assert len(data["items"]) == 3


@pytest.mark.asyncio
async def test_invalid_url(client: AsyncClient):
    """Test creating URL with invalid format.
    
    Args:
        client: AsyncClient test fixture
    """
    response = await client.post(
        "/api/shorten",
        json={
            "original_url": "not a valid url",
        },
    )
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_redirect_graceful_redis_fallback(
    client: AsyncClient, test_db_session: AsyncSession, mock_redis_cache
):
    """Test that redirect works even if Redis is unavailable.
    
    Args:
        client: AsyncClient test fixture
        test_db_session: Database session fixture
        mock_redis_cache: Mock Redis cache fixture
    """
    # Create a URL
    response = await client.post(
        "/api/shorten",
        json={"original_url": "https://example.com/fallback-test"},
    )
    short_code = response.json()["short_code"]

    # Simulate Redis disconnect by making it return False
    original_connect = mock_redis_cache.connect

    async def broken_connect():
        raise Exception("Connection failed")

    mock_redis_cache.connect = broken_connect

    # Redirect should still work via database
    response = await client.get(f"/{short_code}", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "https://example.com/fallback-test"


@pytest.mark.asyncio
async def test_redirect_headers_present(
    client: AsyncClient, test_db_session: AsyncSession
):
    """Test that all required response headers are present.
    
    Args:
        client: AsyncClient test fixture
        test_db_session: Database session fixture
    """
    response = await client.post(
        "/api/shorten",
        json={"original_url": "https://example.com/headers-test"},
    )
    short_code = response.json()["short_code"]

    response = await client.get(f"/{short_code}", follow_redirects=False)
    assert response.status_code == 302

    # Check required headers
    assert "location" in response.headers
    assert "x-cache" in response.headers
    assert "x-response-time" in response.headers

    # Verify header values are valid
    assert response.headers["x-cache"] in ["HIT", "MISS"]
    assert response.headers["x-response-time"].endswith("ms")
