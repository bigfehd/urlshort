"""API routes for analytics endpoints."""
import logging
from datetime import datetime, timedelta, timezone

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
