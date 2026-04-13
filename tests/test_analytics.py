"""Tests for analytics endpoints."""
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ClickEvent, ShortURL


@pytest.mark.asyncio
async def test_get_analytics(client: AsyncClient, test_db_session: AsyncSession):
    """Test getting analytics for a URL.
    
    Args:
        client: AsyncClient test fixture
        test_db_session: Database session fixture
    """
    # Create a URL
    short_url = ShortURL(
        short_code="analytic1",
        original_url="https://www.example.com/analytics-test",
    )
    test_db_session.add(short_url)
    await test_db_session.flush()

    # Add click events
    now = datetime.now(timezone.utc)
    for i in range(5):
        click = ClickEvent(
            short_url_id=short_url.id,
            clicked_at=now - timedelta(days=i),
        )
        test_db_session.add(click)

    short_url.click_count = 5
    await test_db_session.commit()

    # Get analytics
    response = await client.get("/api/analytics/analytic1?days=30")
    assert response.status_code == 200
    data = response.json()
    assert data["short_code"] == "analytic1"
    assert data["total_clicks"] == 5
    assert len(data["data_points"]) > 0


@pytest.mark.asyncio
async def test_analytics_not_found(client: AsyncClient):
    """Test analytics for non-existent URL.
    
    Args:
        client: AsyncClient test fixture
    """
    response = await client.get("/api/analytics/nonexistent?days=30")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_dashboard_summary(client: AsyncClient, test_db_session: AsyncSession):
    """Test dashboard summary endpoint.
    
    Args:
        client: AsyncClient test fixture
        test_db_session: Database session fixture
    """
    # Create URLs
    for i in range(3):
        short_url = ShortURL(
            short_code=f"summary{i}",
            original_url=f"https://www.example.com/url{i}",
            click_count=i + 1,
        )
        test_db_session.add(short_url)
    await test_db_session.commit()

    # Get summary
    response = await client.get("/api/analytics/dashboard/summary?days=30")
    assert response.status_code == 200
    data = response.json()
    assert data["total_urls"] == 3
    assert data["total_clicks"] == 6  # 1 + 2 + 3
    assert "top_urls" in data


@pytest.mark.asyncio
async def test_dashboard_hourly(client: AsyncClient, test_db_session: AsyncSession):
    """Test hourly dashboard data.
    
    Args:
        client: AsyncClient test fixture
        test_db_session: Database session fixture
    """
    # Create a URL
    short_url = ShortURL(
        short_code="hourly",
        original_url="https://www.example.com/hourly",
    )
    test_db_session.add(short_url)
    await test_db_session.flush()

    # Add clicks at different hours
    now = datetime.now(timezone.utc)
    for hour in [0, 6, 12, 18]:
        for _ in range(2):
            click = ClickEvent(
                short_url_id=short_url.id,
                clicked_at=now.replace(hour=hour, minute=0, second=0),
            )
            test_db_session.add(click)
    await test_db_session.commit()

    # Get hourly data
    response = await client.get("/api/analytics/dashboard/hourly?days=1")
    assert response.status_code == 200
    data = response.json()
    assert "hourly_distribution" in data
    assert len(data["hourly_distribution"]) == 24
