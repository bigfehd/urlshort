"""Tests for URL shortening endpoints."""
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
async def test_redirect_cache_hit(client: AsyncClient, test_db_session: AsyncSession):
    """Test redirect with cache hit.
    
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

    # First redirect (cache miss, populates cache)
    response1 = await client.get(f"/{short_code}", follow_redirects=False)
    assert response1.status_code == 302
    assert response1.headers["location"] == "https://www.example.com/cache-test"

    # Second redirect (cache hit)
    response2 = await client.get(f"/{short_code}", follow_redirects=False)
    assert response2.status_code == 302
    assert response2.headers["location"] == "https://www.example.com/cache-test"


@pytest.mark.asyncio
async def test_redirect_cache_miss(client: AsyncClient, test_db_session: AsyncSession):
    """Test redirect direct from database (cache miss).
    
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

    # Redirect should work even without cache
    response = await client.get("/testcode", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "https://www.example.com/cache-miss-test"


@pytest.mark.asyncio
async def test_redirect_not_found(client: AsyncClient):
    """Test redirect with non-existent short code.
    
    Args:
        client: AsyncClient test fixture
    """
    response = await client.get("/nonexistent", follow_redirects=False)
    assert response.status_code == 404


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
