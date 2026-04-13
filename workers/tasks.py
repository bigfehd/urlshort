"""Celery tasks for asynchronous event processing."""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models import ClickEvent, ShortURL
from config import get_settings
from workers.config import celery_app

logger = logging.getLogger(__name__)
settings = get_settings()

# Create async engine for Celery tasks
engine = create_async_engine(settings.database_dsn, future=True)
async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_click_event(
    self,
    short_url_id: int,
    user_agent: Optional[str] = None,
    referrer: Optional[str] = None,
    ip_address: Optional[str] = None,
    device_type: Optional[str] = None,
) -> dict:
    """Process a click event asynchronously.
    
    This task:
    1. Creates a ClickEvent record in the database
    2. Updates the ShortURL click count
    3. Updates last_accessed_at timestamp
    4. Stores device type classification
    
    Args:
        short_url_id: ID of the shortened URL that was clicked
        user_agent: HTTP User-Agent header
        referrer: HTTP Referrer header
        ip_address: Client IP address
        device_type: Device type (mobile, desktop, bot)
        
    Returns:
        Task result dictionary with status and details
    """
    try:
        # Import here to avoid circular imports
        from sqlalchemy import func

        # Run async operations in event loop
        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _process_click_event_async(
                    short_url_id, user_agent, referrer, ip_address, device_type
                )
            )
            return result
        finally:
            loop.close()

    except Exception as exc:
        logger.exception(f"Error processing click event for URL {short_url_id}: {exc}")
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)


async def _process_click_event_async(
    short_url_id: int,
    user_agent: Optional[str] = None,
    referrer: Optional[str] = None,
    ip_address: Optional[str] = None,
    device_type: Optional[str] = None,
) -> dict:
    """Async implementation of click event processing.
    
    Args:
        short_url_id: ID of the shortened URL
        user_agent: HTTP User-Agent
        referrer: HTTP Referrer
        ip_address: Client IP address
        device_type: Device type classification
        
    Returns:
        Result dictionary
    """
    async with async_session_maker() as session:
        try:
            # Create click event record
            click_event = ClickEvent(
                short_url_id=short_url_id,
                user_agent=user_agent,
                referrer=referrer,
                ip_address=ip_address,
                device_type=device_type or "desktop",
                clicked_at=datetime.now(timezone.utc),
            )
            session.add(click_event)

            # Update ShortURL click count and last_accessed_at
            stmt = (
                update(ShortURL)
                .where(ShortURL.id == short_url_id)
                .values(
                    click_count=ShortURL.click_count + 1,
                    last_accessed_at=datetime.now(timezone.utc),
                )
            )
            await session.execute(stmt)

            await session.commit()

            logger.info(
                f"Click event processed for short_url_id: {short_url_id}, device: {device_type}"
            )
            return {
                "status": "success",
                "short_url_id": short_url_id,
                "click_event_id": click_event.id,
                "device_type": device_type,
            }

        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to process click event: {e}")
            raise


@celery_app.task
def cleanup_old_click_events(days: int = 90) -> dict:
    """Clean up old click events from database.
    
    Args:
        days: Delete click events older than this many days
        
    Returns:
        Result dictionary with count of deleted records
    """
    import asyncio

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(_cleanup_old_click_events_async(days))
        return result
    finally:
        loop.close()


async def _cleanup_old_click_events_async(days: int) -> dict:
    """Async implementation of cleanup.
    
    Args:
        days: Days threshold
        
    Returns:
        Result dictionary
    """
    from datetime import timedelta

    async with async_session_maker() as session:
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

            stmt = select(ClickEvent).where(ClickEvent.clicked_at < cutoff_date)
            result = await session.execute(stmt)
            old_events = result.scalars().all()
            count = len(old_events)

            for event in old_events:
                await session.delete(event)

            await session.commit()

            logger.info(f"Cleaned up {count} old click events (older than {days} days)")
            return {"status": "success", "deleted_count": count}

        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to cleanup click events: {e}")
            raise
