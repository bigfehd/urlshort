"""API routes for URL shortening endpoints."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cache, get_redirect_cache_key, get_url_info_cache_key
from app.database import get_db_session
from app.metrics import cache_hits, cache_misses, redirects_total
from app.models import ClickEvent, ShortURL
from app.schemas import (
    CreateShortURLRequest,
    CreateShortURLResponse,
    ShortURLResponse,
)
from app.utils import generate_short_code, get_client_ip
from config import get_settings
from workers.config import celery_app

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/api", tags=["urls"])


@router.post("/shorten", response_model=CreateShortURLResponse)
async def create_short_url(
    request: CreateShortURLRequest,
    session: AsyncSession = Depends(get_db_session),
) -> CreateShortURLResponse:
    """Create a shortened URL.
    
    Args:
        request: Request body containing original URL and optional description
        session: Database session
        
    Returns:
        Created short URL details
        
    Raises:
        HTTPException: If URL is invalid or database operation fails
    """
    try:
        # Create new ShortURL record
        short_url = ShortURL(
            original_url=str(request.original_url),
            description=request.description,
        )
        session.add(short_url)
        await session.flush()  # Flush to get the ID without committing

        # Generate short code from primary key (Base62)
        short_code = generate_short_code(short_url.id)
        short_url.short_code = short_code

        await session.commit()

        # Cache the redirect
        cache_key = get_redirect_cache_key(short_code)
        await cache.set(cache_key, str(request.original_url))

        logger.info(f"Created short URL: {short_code} -> {request.original_url}")

        return CreateShortURLResponse(
            short_code=short_code,
            short_url=f"{settings.BASE_URL}/{short_code}",
            original_url=str(request.original_url),
        )

    except Exception as e:
        await session.rollback()
        logger.error(f"Error creating short URL: {e}")
        raise HTTPException(status_code=500, detail="Failed to create short URL")


@router.get("/{short_code}")
async def redirect(
    short_code: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """Redirect to original URL by short code.
    
    Uses cache-aside pattern:
    1. Try to get redirect URL from cache
    2. If not in cache, query database
    3. Cache the result
    
    Args:
        short_code: The short code
        request: HTTP request (for metrics)
        session: Database session
        
    Returns:
        Redirect response to original URL
        
    Raises:
        HTTPException: If short code not found
    """
    logger.debug(f"Redirect request for: {short_code}")

    # Try cache first (cache-aside pattern)
    cache_key = get_redirect_cache_key(short_code)
    original_url = await cache.get(cache_key)

    if original_url:
        logger.debug(f"Cache hit for: {short_code}")
        cache_hits.inc()
        status_code = 200
    else:
        logger.debug(f"Cache miss for: {short_code}")
        cache_misses.inc()

        # Query database
        stmt = select(ShortURL).where(ShortURL.short_code == short_code)
        result = await session.execute(stmt)
        short_url = result.scalar_one_or_none()

        if not short_url:
            logger.warning(f"Short code not found: {short_code}")
            raise HTTPException(status_code=404, detail="URL not found")

        original_url = short_url.original_url
        status_code = 200

        # Cache for future requests
        await cache.set(cache_key, original_url)

    # Extract client information
    headers_dict = dict(request.headers)
    user_agent = headers_dict.get("user-agent")
    referrer = headers_dict.get("referer")
    ip_address = get_client_ip(headers_dict)

    # Record click event asynchronously
    # Get the ShortURL ID if not already available
    if not original_url:
        stmt = select(ShortURL.id).where(ShortURL.short_code == short_code)
        result = await session.execute(stmt)
        short_url_id = result.scalar_one_or_none()
    else:
        # If we got from cache, we need to query the ID
        stmt = select(ShortURL.id).where(ShortURL.short_code == short_code)
        result = await session.execute(stmt)
        short_url_id = result.scalar_one_or_none()

    if short_url_id:
        # Send async task to Celery
        celery_app.send_task(
            "workers.tasks.process_click_event",
            args=[short_url_id],
            kwargs={
                "user_agent": user_agent,
                "referrer": referrer,
                "ip_address": ip_address,
            },
        )

        redirects_total.labels(short_code=short_code, status=status_code).inc()

    logger.info(f"Redirecting {short_code} to {original_url}")

    return Response(
        status_code=302,
        headers={"Location": str(original_url)},
    )


@router.get("/info/{short_code}", response_model=ShortURLResponse)
async def get_url_info(
    short_code: str,
    session: AsyncSession = Depends(get_db_session),
) -> ShortURLResponse:
    """Get information about a shortened URL.
    
    Args:
        short_code: The short code
        session: Database session
        
    Returns:
        URL information
        
    Raises:
        HTTPException: If short code not found
    """
    stmt = select(ShortURL).where(ShortURL.short_code == short_code)
    result = await session.execute(stmt)
    short_url = result.scalar_one_or_none()

    if not short_url:
        raise HTTPException(status_code=404, detail="URL not found")

    return ShortURLResponse(
        id=short_url.id,
        short_code=short_url.short_code,
        original_url=short_url.original_url,
        description=short_url.description,
        short_url=f"{settings.BASE_URL}/{short_url.short_code}",
        click_count=short_url.click_count,
        created_at=short_url.created_at,
        updated_at=short_url.updated_at,
        last_accessed_at=short_url.last_accessed_at,
    )


@router.get("/list")
async def list_urls(
    limit: int = 20,
    offset: int = 0,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """List all shortened URLs with pagination.
    
    Args:
        limit: Maximum number of results
        offset: Pagination offset
        session: Database session
        
    Returns:
        List of URLs and total count
    """
    # Get total count
    count_stmt = select(func.count(ShortURL.id))
    total = await session.execute(count_stmt)
    total_count = total.scalar()

    # Get paginated results
    stmt = (
        select(ShortURL)
        .order_by(ShortURL.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    urls = result.scalars().all()

    return {
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "items": [
            ShortURLResponse(
                id=url.id,
                short_code=url.short_code,
                original_url=url.original_url,
                description=url.description,
                short_url=f"{settings.BASE_URL}/{url.short_code}",
                click_count=url.click_count,
                created_at=url.created_at,
                updated_at=url.updated_at,
                last_accessed_at=url.last_accessed_at,
            )
            for url in urls
        ],
    }
