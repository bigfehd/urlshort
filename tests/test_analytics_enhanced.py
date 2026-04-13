"""Tests for enhanced analytics endpoints with hourly data and device tracking."""
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ClickEvent, ShortURL


@pytest.mark.asyncio
async def test_top_urls_24h(client: AsyncClient, test_db_session: AsyncSession):
    """Test getting top URLs in last 24 hours.
    
    Args:
        client: AsyncClient test fixture
        test_db_session: Database session fixture
    """
    # Create multiple URLs
    now = datetime.now(timezone.utc)
    for i in range(3):
        short_url = ShortURL(
            short_code=f"top{i}",
            original_url=f"https://example.com/url{i}",
            click_count=i + 1,
        )
        test_db_session.add(short_url)
        await test_db_session.flush()

        # Add clicks with varied timing
        for j in range(i + 1):
            click = ClickEvent(
                short_url_id=short_url.id,
                clicked_at=now - timedelta(hours=12),
                device_type="desktop" if j == 0 else "mobile",
            )
            test_db_session.add(click)

    await test_db_session.commit()

    # Get top URLs
    response = await client.get("/api/analytics/popular/24h?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert data["period"] == "last_24_hours"
    assert len(data["top_urls"]) == 3
    assert data["top_urls"][0]["click_count"] >= data["top_urls"][1]["click_count"]
    # Check device breakdown exists
    assert "device_breakdown" in data["top_urls"][0]
    assert "desktop" in data["top_urls"][0]["device_breakdown"]


@pytest.mark.asyncio
async def test_hourly_analytics_7days(client: AsyncClient, test_db_session: AsyncSession):
    """Test hourly analytics for 7 days.
    
    Args:
        client: AsyncClient test fixture
        test_db_session: Database session fixture
    """
    # Create a URL
    short_url = ShortURL(
        short_code="hourly7d",
        original_url="https://example.com/hourly",
    )
    test_db_session.add(short_url)
    await test_db_session.flush()

    # Add clicks at different hours for 7 days
    now = datetime.now(timezone.utc)
    for day in range(7):
        for hour in [0, 6, 12, 18]:
            for _ in range(2):
                click = ClickEvent(
                    short_url_id=short_url.id,
                    clicked_at=now - timedelta(days=day) + timedelta(hours=hour),
                    device_type="mobile" if _ == 0 else "desktop",
                )
                test_db_session.add(click)

    await test_db_session.commit()

    # Get hourly analytics
    response = await client.get("/api/analytics/hourly7d/hourly-7d")
    assert response.status_code == 200
    data = response.json()
    assert data["short_code"] == "hourly7d"
    assert data["period_days"] == 7
    assert len(data["hourly_data"]) > 0
    # Check structure of hourly data
    first_hour = data["hourly_data"][0]
    assert "timestamp" in first_hour
    assert "clicks" in first_hour
    assert "devices" in first_hour


@pytest.mark.asyncio
async def test_device_analytics(client: AsyncClient, test_db_session: AsyncSession):
    """Test device type analytics.
    
    Args:
        client: AsyncClient test fixture
        test_db_session: Database session fixture
    """
    # Create a URL
    short_url = ShortURL(
        short_code="devices",
        original_url="https://example.com/devices",
    )
    test_db_session.add(short_url)
    await test_db_session.flush()

    # Add clicks from different devices
    now = datetime.now(timezone.utc)
    devices = ["desktop", "desktop", "desktop", "mobile", "mobile", "bot"]
    for device in devices:
        click = ClickEvent(
            short_url_id=short_url.id,
            clicked_at=now,
            device_type=device,
        )
        test_db_session.add(click)

    await test_db_session.commit()

    # Get device analytics
    response = await client.get("/api/analytics/devices/device-analytics?days=7")
    assert response.status_code == 200
    data = response.json()
    assert data["short_code"] == "devices"
    assert data["total_clicks"] == 6
    
    # Check device distribution
    assert data["device_distribution"]["desktop"]["count"] == 3
    assert data["device_distribution"]["mobile"]["count"] == 2
    assert data["device_distribution"]["bot"]["count"] == 1
    
    # Check percentages
    assert round(data["device_distribution"]["desktop"]["percentage"], 1) == 50.0
    assert round(data["device_distribution"]["mobile"]["percentage"], 1) == 33.3
    assert round(data["device_distribution"]["bot"]["percentage"], 1) == 16.7


@pytest.mark.asyncio
async def test_clicks_per_minute(client: AsyncClient, mock_redis_cache):
    """Test clicks per minute endpoint.
    
    Args:
        client: AsyncClient test fixture
        mock_redis_cache: Mock Redis cache fixture
    """
    # Test global clicks per minute (no specific short_code)
    response = await client.get("/api/analytics/realtime/clicks-per-minute")
    assert response.status_code == 200
    data = response.json()
    assert data["period_seconds"] == 60
    assert "clicks_per_minute" in data
    assert "average_clicks_per_second" in data


@pytest.mark.asyncio
async def test_clicks_per_minute_specific_url(
    client: AsyncClient, test_db_session: AsyncSession
):
    """Test clicks per minute for specific URL.
    
    Args:
        client: AsyncClient test fixture
        test_db_session: Database session fixture
    """
    # Create a URL
    short_url = ShortURL(
        short_code="cpm",
        original_url="https://example.com/cpm",
    )
    test_db_session.add(short_url)
    await test_db_session.commit()

    # Test specific URL's clicks per minute
    response = await client.get("/api/analytics/realtime/clicks-per-minute?short_code=cpm")
    assert response.status_code == 200
    data = response.json()
    assert data["short_code"] == "cpm"


@pytest.mark.asyncio
async def test_clicks_per_minute_not_found(client: AsyncClient):
    """Test clicks per minute for non-existent URL.
    
    Args:
        client: AsyncClient test fixture
    """
    response = await client.get(
        "/api/analytics/realtime/clicks-per-minute?short_code=nonexistent"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_device_type_parser():
    """Test device type detection from user agents."""
    from app.utils import UserAgentParser

    # Test desktop
    assert (
        UserAgentParser.detect_device_type(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        == "desktop"
    )

    # Test mobile
    assert (
        UserAgentParser.detect_device_type(
            "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)"
        )
        == "mobile"
    )
    assert (
        UserAgentParser.detect_device_type("Mozilla/5.0 (Linux; Android 10)")
        == "mobile"
    )

    # Test bot
    assert UserAgentParser.detect_device_type("Mozilla/5.0 (compatible; Googlebot)") == "bot"
    assert UserAgentParser.detect_device_type("curl/7.64.1") == "bot"
    assert UserAgentParser.detect_device_type("python-requests/2.28.0") == "bot"

    # Test None/empty
    assert UserAgentParser.detect_device_type(None) == "desktop"
    assert UserAgentParser.detect_device_type("") == "desktop"


@pytest.mark.asyncio
async def test_sliding_window_counter(mock_redis_cache):
    """Test sliding window counter functionality.
    
    Args:
        mock_redis_cache: Mock Redis cache fixture
    """
    await mock_redis_cache.connect()

    # Test increment sliding window
    count1 = await mock_redis_cache.increment_sliding_window("test_window", window_seconds=60)
    assert count1 == 1

    count2 = await mock_redis_cache.increment_sliding_window("test_window", window_seconds=60)
    assert count2 == 2

    # Test get sliding window count
    count3 = await mock_redis_cache.get_sliding_window_count("test_window", window_seconds=60)
    assert count3 == 2
