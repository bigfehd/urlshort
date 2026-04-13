"""API routes for analytics endpoints."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.models import ClickEvent, ShortURL
from app.schemas import AnalyticsDataPoint, AnalyticsResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/{short_code}", response_model=AnalyticsResponse)
async def get_analytics(
    short_code: str,
    days: int = 30,
    session: AsyncSession = Depends(get_db_session),
) -> AnalyticsResponse:
    """Get analytics for a shortened URL.
    
    Returns click counts aggregated by day for the specified time period.
    
    Args:
        short_code: The short code
        days: Number of days to analyze (default: 30)
        session: Database session
        
    Returns:
        Analytics data including click trends
        
    Raises:
        HTTPException: If short code not found
    """
    # Get the ShortURL
    stmt = select(ShortURL).where(ShortURL.short_code == short_code)
    result = await session.execute(stmt)
    short_url = result.scalar_one_or_none()

    if not short_url:
        raise HTTPException(status_code=404, detail="URL not found")

    # Get click events for the specified period
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

    stmt = select(ClickEvent).where(
        and_(
            ClickEvent.short_url_id == short_url.id,
            ClickEvent.clicked_at >= cutoff_date,
        )
    )
    result = await session.execute(stmt)
    click_events = result.scalars().all()

    # Aggregate clicks by day
    daily_clicks: dict[datetime, int] = {}
    for event in click_events:
        # Normalize to day start (UTC)
        day_start = event.clicked_at.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        daily_clicks[day_start] = daily_clicks.get(day_start, 0) + 1

    # Create data points sorted by date
    data_points = [
        AnalyticsDataPoint(timestamp=day, click_count=count)
        for day, count in sorted(daily_clicks.items())
    ]

    logger.info(
        f"Retrieved analytics for {short_code}: "
        f"{len(click_events)} clicks in {days} days"
    )

    return AnalyticsResponse(
        short_code=short_code,
        original_url=short_url.original_url,
        total_clicks=short_url.click_count,
        created_at=short_url.created_at,
        last_accessed_at=short_url.last_accessed_at,
        data_points=data_points,
    )


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    days: int = 30,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Get summary statistics for the dashboard.
    
    Args:
        days: Number of days to analyze
        session: Database session
        
    Returns:
        Summary statistics
    """
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

    # Total URLs
    total_urls_stmt = select(func.count(ShortURL.id))
    total_urls = await session.execute(total_urls_stmt)
    total_urls_count = total_urls.scalar()

    # Total clicks
    total_clicks_stmt = select(func.sum(ShortURL.click_count))
    total_clicks = await session.execute(total_clicks_stmt)
    total_clicks_count = total_clicks.scalar() or 0

    # New URLs in period
    new_urls_stmt = select(func.count(ShortURL.id)).where(
        ShortURL.created_at >= cutoff_date
    )
    new_urls = await session.execute(new_urls_stmt)
    new_urls_count = new_urls.scalar()

    # New clicks in period
    new_clicks_stmt = select(func.count(ClickEvent.id)).where(
        ClickEvent.clicked_at >= cutoff_date
    )
    new_clicks = await session.execute(new_clicks_stmt)
    new_clicks_count = new_clicks.scalar() or 0

    # Top URLs by clicks
    top_urls_stmt = (
        select(ShortURL.short_code, ShortURL.original_url, ShortURL.click_count)
        .order_by(ShortURL.click_count.desc())
        .limit(10)
    )
    top_urls = await session.execute(top_urls_stmt)
    top_urls_list = [
        {
            "short_code": row[0],
            "original_url": row[1],
            "click_count": row[2],
        }
        for row in top_urls.all()
    ]

    return {
        "total_urls": total_urls_count,
        "total_clicks": total_clicks_count,
        "new_urls": new_urls_count,
        "new_clicks": new_clicks_count,
        "period_days": days,
        "top_urls": top_urls_list,
    }


@router.get("/dashboard/hourly")
async def get_hourly_clicks(
    days: int = 1,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Get hourly click distribution for dashboard.
    
    Args:
        days: Number of days to analyze (default: 1)
        session: Database session
        
    Returns:
        Hourly click distribution
    """
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

    # Get all click events for the period
    stmt = select(ClickEvent).where(ClickEvent.clicked_at >= cutoff_date)
    result = await session.execute(stmt)
    events = result.scalars().all()

    # Aggregate by hour
    hourly_clicks: dict[int, int] = {hour: 0 for hour in range(24)}
    for event in events:
        hour = event.clicked_at.hour
        hourly_clicks[hour] = hourly_clicks.get(hour, 0) + 1

    return {
        "period_days": days,
        "hourly_distribution": [
            {"hour": hour, "clicks": hourly_clicks[hour]} for hour in range(24)
        ],
    }


@router.get("/popular/24h", tags=["analytics"])
async def get_top_urls_24h(
    limit: int = 10,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Get top clicked URLs in the last 24 hours.
    
    Returns the most popular links based on click count in the recent period.
    
    Args:
        limit: Number of top URLs to return (default: 10, max: 100)
        session: Database session
        
    Returns:
        List of top URLs with click counts
        
    Example:
        ```json
        {
          "period": "last_24_hours",
          "returned_count": 5,
          "top_urls": [
            {
              "short_code": "abc123",
              "original_url": "https://example.com/...",
              "click_count": 150,
              "device_breakdown": {
                "desktop": 90,
                "mobile": 55,
                "bot": 5
              }
            }
          ]
        }
        ```
    """
    limit = min(limit, 100)  # Cap at 100
    cutoff_date = datetime.now(timezone.utc) - timedelta(hours=24)

    # Get top URLs by recent clicks
    stmt = (
        select(
            ShortURL.short_code,
            ShortURL.original_url,
            func.count(ClickEvent.id).label("recent_clicks"),
        )
        .join(ClickEvent, ShortURL.id == ClickEvent.short_url_id)
        .where(ClickEvent.clicked_at >= cutoff_date)
        .group_by(ShortURL.id, ShortURL.short_code, ShortURL.original_url)
        .order_by(func.count(ClickEvent.id).desc())
        .limit(limit)
    )

    result = await session.execute(stmt)
    top_urls_rows = result.all()

    # For each URL, get device breakdown
    top_urls_list = []
    for short_code, original_url, recent_clicks in top_urls_rows:
        # Get device breakdown for this URL
        device_stmt = (
            select(ClickEvent.device_type, func.count(ClickEvent.id).label("count"))
            .where(
                and_(
                    ClickEvent.short_url_id == (
                        select(ShortURL.id).where(ShortURL.short_code == short_code)
                    ),
                    ClickEvent.clicked_at >= cutoff_date,
                )
            )
            .group_by(ClickEvent.device_type)
        )
        device_result = await session.execute(device_stmt)
        device_breakdown = {
            device: count for device, count in device_result.all()
        }

        top_urls_list.append(
            {
                "short_code": short_code,
                "original_url": original_url,
                "click_count": recent_clicks,
                "device_breakdown": {
                    "desktop": device_breakdown.get("desktop", 0),
                    "mobile": device_breakdown.get("mobile", 0),
                    "bot": device_breakdown.get("bot", 0),
                },
            }
        )

    return {
        "period": "last_24_hours",
        "returned_count": len(top_urls_list),
        "top_urls": top_urls_list,
    }


@router.get("/{short_code}/hourly-7d", tags=["analytics"])
async def get_hourly_analytics_7days(
    short_code: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Get hourly click analytics for a URL over the last 7 days.
    
    Provides detailed hour-by-hour breakdown of clicks for trend analysis.
    
    Args:
        short_code: The short code
        session: Database session
        
    Returns:
        Hourly click data for 7 days
        
    Raises:
        HTTPException: If short code not found
        
    Example:
        ```json
        {
          "short_code": "abc123",
          "period_days": 7,
          "total_clicks": 1234,
          "hourly_data": [
            {
              "timestamp": "2024-01-15T00:00:00Z",
              "hour": 0,
              "clicks": 12,
              "devices": {
                "desktop": 8,
                "mobile": 4,
                "bot": 0
              }
            }
          ]
        }
        ```
    """
    # Verify short code exists
    stmt = select(ShortURL.id).where(ShortURL.short_code == short_code)
    result = await session.execute(stmt)
    short_url_id = result.scalar_one_or_none()

    if not short_url_id:
        raise HTTPException(status_code=404, detail="URL not found")

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=7)

    # Get all click events for this URL in the period
    stmt = select(ClickEvent).where(
        and_(
            ClickEvent.short_url_id == short_url_id,
            ClickEvent.clicked_at >= cutoff_date,
        )
    )
    result = await session.execute(stmt)
    events = result.scalars().all()

    # Aggregate by hour
    hourly_data: dict[datetime, dict] = {}
    for event in events:
        # Normalize to hour start
        hour_start = event.clicked_at.replace(minute=0, second=0, microsecond=0)

        if hour_start not in hourly_data:
            hourly_data[hour_start] = {
                "clicks": 0,
                "devices": {"desktop": 0, "mobile": 0, "bot": 0},
            }

        hourly_data[hour_start]["clicks"] += 1
        hourly_data[hour_start]["devices"][event.device_type] = (
            hourly_data[hour_start]["devices"].get(event.device_type, 0) + 1
        )

    # Sort by timestamp
    sorted_hours = sorted(hourly_data.items())

    return {
        "short_code": short_code,
        "period_days": 7,
        "total_clicks": len(events),
        "hourly_data": [
            {
                "timestamp": hour.isoformat(),
                "hour": hour.hour,
                "clicks": data["clicks"],
                "devices": data["devices"],
            }
            for hour, data in sorted_hours
        ],
    }


@router.get("/{short_code}/device-analytics", tags=["analytics"])
async def get_device_analytics(
    short_code: str,
    days: int = 7,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Get device type analytics for a shortened URL.
    
    Shows breakdown of clicks by device type (mobile, desktop, bot).
    
    Args:
        short_code: The short code
        days: Number of days to analyze (default: 7)
        session: Database session
        
    Returns:
        Device type distribution and statistics
        
    Raises:
        HTTPException: If short code not found
        
    Example:
        ```json
        {
          "short_code": "abc123",
          "period_days": 7,
          "total_clicks": 1000,
          "device_distribution": {
            "desktop": {
              "count": 650,
              "percentage": 65.0
            },
            "mobile": {
              "count": 320,
              "percentage": 32.0
            },
            "bot": {
              "count": 30,
              "percentage": 3.0
            }
          }
        }
        ```
    """
    # Verify short code exists
    stmt = select(ShortURL).where(ShortURL.short_code == short_code)
    result = await session.execute(stmt)
    short_url = result.scalar_one_or_none()

    if not short_url:
        raise HTTPException(status_code=404, detail="URL not found")

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

    # Get device distribution
    stmt = (
        select(ClickEvent.device_type, func.count(ClickEvent.id).label("count"))
        .where(
            and_(
                ClickEvent.short_url_id == short_url.id,
                ClickEvent.clicked_at >= cutoff_date,
            )
        )
        .group_by(ClickEvent.device_type)
    )
    result = await session.execute(stmt)
    device_counts = dict(result.all())

    total_clicks = sum(device_counts.values())
    if total_clicks == 0:
        total_clicks = 1  # Avoid division by zero

    return {
        "short_code": short_code,
        "period_days": days,
        "total_clicks": total_clicks,
        "device_distribution": {
            "desktop": {
                "count": device_counts.get("desktop", 0),
                "percentage": round(
                    (device_counts.get("desktop", 0) / total_clicks) * 100, 2
                ),
            },
            "mobile": {
                "count": device_counts.get("mobile", 0),
                "percentage": round(
                    (device_counts.get("mobile", 0) / total_clicks) * 100, 2
                ),
            },
            "bot": {
                "count": device_counts.get("bot", 0),
                "percentage": round(
                    (device_counts.get("bot", 0) / total_clicks) * 100, 2
                ),
            },
        },
    }


@router.get("/realtime/clicks-per-minute", tags=["analytics"])
async def get_clicks_per_minute(
    short_code: Optional[str] = None,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Get real-time clicks per minute (last 60 seconds).
    
    Returns current click rate from Redis sliding window counter.
    Useful for monitoring spikes and real-time dashboards.
    
    Args:
        short_code: Optional specific URL to monitor. If None, returns system-wide.
        session: Database session
        
    Returns:
        Clicks per minute count
        
    Example:
        ```json
        {
          "period_seconds": 60,
          "clicks_per_minute": 42,
          "short_code": "abc123",
          "average_clicks_per_second": 0.7
        }
        ```
    """
    from app.cache import cache

    if short_code:
        # Verify short code exists
        stmt = select(ShortURL.id).where(ShortURL.short_code == short_code)
        result = await session.execute(stmt)
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="URL not found")

        # Get sliding window count for this specific URL
        cache_key = f"clicks_per_minute:url:{short_code}"
    else:
        # Get global sliding window count
        cache_key = "clicks_per_minute:global"

    count = await cache.get_sliding_window_count(cache_key, window_seconds=60)

    return {
        "period_seconds": 60,
        "clicks_per_minute": count,
        "short_code": short_code,
        "average_clicks_per_second": round(count / 60, 2),
    }
