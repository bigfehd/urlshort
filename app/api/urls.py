"""API routes for URL shortening endpoints."""
import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cache, get_redirect_cache_key, get_url_info_cache_key
from app.database import get_db_session
from app.metrics import cache_hits, cache_misses, redirects_total, urls_created_total
from app.models import ShortURL
from app.schemas import (
    CreateShortURLRequest,
    CreateShortURLResponse,
    ShortURLResponse,
)
from app.utils import UserAgentParser, generate_short_code, get_client_ip
from config import get_settings
from workers.config import celery_app

logger = logging.getLogger(__name__)
# Structured JSON logger for redirect events
redirect_logger = logging.getLogger("urlshort.redirects")
settings = get_settings()

router = APIRouter(prefix="/api", tags=["urls"])


async def check_rate_limit(request: Request) -> None:
    """Check rate limit for create_short_url endpoint.
    
    Rate limit: 20 requests per minute per IP
    
    Args:
        request: HTTP request
        
    Raises:
        HTTPException: If rate limit exceeded
    """
    try:
        client_ip = get_client_ip(dict(request.headers))
        rate_limit_key = f"rate_limit:shorten:{client_ip}"
        
        # Increment counter (expires after 60 seconds)
        current_count = await cache.incr(rate_limit_key)
        if current_count == 1:
            # Set expiry only on first request
            await cache.expire(rate_limit_key, 60)
        
        if current_count > 20:
            logger.warning(f"Rate limit exceeded for IP {client_ip}: {current_count} requests")
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded: maximum 20 requests per minute",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Rate limit check failed (allowing request): {e}")



@router.post("/shorten", response_model=CreateShortURLResponse)
async def create_short_url(
    request: CreateShortURLRequest,
    http_request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> CreateShortURLResponse:
    """Create a shortened URL with rate limiting.
    
    Rate limit: 20 requests per minute per IP
    
    Args:
        request: Request body containing original URL and optional description
        http_request: HTTP request (for rate limiting)
        session: Database session
        
    Returns:
        Created short URL details
        
    Raises:
        HTTPException: If URL is invalid, rate limited, or database operation fails
    """
    # Check rate limit
    await check_rate_limit(http_request)
    
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

        # Track metric
        urls_created_total.inc()

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
    """Redirect to original URL by short code with optimized cache-aside pattern.
    
    Features:
    - Redis pipeline for efficient cache operations
    - Graceful fallback to PostgreSQL if Redis is unavailable
    - Response headers indicating cache hit/miss and latency
    - Structured JSON logging for every redirect
    
    Args:
        short_code: The short code
        request: HTTP request (for metrics and client info)
        session: Database session
        
    Returns:
        Redirect response to original URL with cache/timing headers
        
    Raises:
        HTTPException: If short code not found
    """
    start_time = time.time()
    cache_key = get_redirect_cache_key(short_code)
    original_url = None
    short_url_id = None
    cache_hit = False
    redis_available = True

    # Extract client information upfront
    headers_dict = dict(request.headers)
    user_agent = headers_dict.get("user-agent")
    referrer = headers_dict.get("referer")
    ip_address = get_client_ip(headers_dict)

    # Try cache first using pipelined operation
    try:
        original_url, cache_hit = await cache.pipeline_get_and_enqueue(cache_key)
        if cache_hit:
            cache_hits.inc()
    except Exception as e:
        logger.warning(f"Redis pipeline error: {e}, falling back to database")
        redis_available = False

    # If not in cache or Redis is unavailable, query database
    if not original_url:
        if cache_hit:
            # Cache miss
            cache_misses.inc()
        
        try:
            stmt = select(ShortURL).where(ShortURL.short_code == short_code)
            result = await session.execute(stmt)
            short_url = result.scalar_one_or_none()

            if not short_url:
                logger.warning(f"Short code not found: {short_code}")
                raise HTTPException(status_code=404, detail="URL not found")

            original_url = short_url.original_url
            short_url_id = short_url.id

            # Try to cache for future requests (fail gracefully if Redis is down)
            if redis_available:
                try:
                    await cache.pipeline_set(cache_key, original_url)
                except Exception as e:
                    logger.warning(f"Failed to cache redirect: {e}")
                    redis_available = False
            else:
                cache_misses.inc()

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Database error during redirect: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    # If we got from cache but still need the ID for click tracking
    if cache_hit and not short_url_id:
        try:
            stmt = select(ShortURL.id).where(ShortURL.short_code == short_code)
            result = await session.execute(stmt)
            short_url_id = result.scalar_one_or_none()
        except Exception as e:
            logger.warning(f"Failed to get short_url_id for click tracking: {e}")

    # Calculate response time
    latency_ms = round((time.time() - start_time) * 1000, 2)

    # Record click event asynchronously (fire and forget)
    if short_url_id:
        try:
            # Detect device type from user agent
            device_type = UserAgentParser.detect_device_type(user_agent)
            
            # Track clicks per minute (in Redis)
            try:
                # Global clicks per minute
                await cache.increment_sliding_window("clicks_per_minute:global", window_seconds=60)
                # URL-specific clicks per minute
                await cache.increment_sliding_window(
                    f"clicks_per_minute:url:{short_code}", window_seconds=60
                )
            except Exception as e:
                logger.warning(f"Failed to update sliding window counters: {e}")
            
            celery_app.send_task(
                "workers.tasks.process_click_event",
                args=[short_url_id],
                kwargs={
                    "user_agent": user_agent,
                    "referrer": referrer,
                    "ip_address": ip_address,
                    "device_type": device_type,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to enqueue click event: {e}")

        redirects_total.labels(short_code=short_code, status=302).inc()

    # Structured JSON logging for redirect events
    device_type = UserAgentParser.detect_device_type(user_agent)
    redirect_event = {
        "short_code": short_code,
        "cache_hit": cache_hit,
        "redis_available": redis_available,
        "latency_ms": latency_ms,
        "user_agent": user_agent,
        "device_type": device_type,
        "ip_address": ip_address,
        "original_url": original_url[:50] if original_url else None,  # Truncate for logs
    }
    redirect_logger.info(json.dumps(redirect_event))

    # Build response with performance headers
    response_headers = {
        "Location": str(original_url),
        "X-Cache": "HIT" if cache_hit else "MISS",
        "X-Response-Time": f"{latency_ms}ms",
    }

    return Response(
        status_code=302,
        headers=response_headers,
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
