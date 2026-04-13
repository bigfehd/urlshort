"""API routes for health checks and system status."""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cache
from app.database import get_db_session
from app.schemas import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check(session: AsyncSession = Depends(get_db_session)) -> HealthResponse:
    """Health check endpoint.
    
    Checks the status of:
    - Application
    - Database connection
    - Redis cache connection
    
    Args:
        session: Database session
        
    Returns:
        Health status
    """
    # Check database
    try:
        await session.execute("SELECT 1")
        db_status = "healthy"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "unhealthy"

    # Check Redis
    try:
        redis_status = "healthy" if await cache.is_connected() else "unhealthy"
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        redis_status = "unhealthy"

    return HealthResponse(
        status="healthy" if db_status == "healthy" and redis_status == "healthy" else "degraded",
        version="1.0.0",
        database=db_status,
        redis=redis_status,
    )


@router.get("/metrics")
async def metrics() -> bytes:
    """Prometheus metrics endpoint.
    
    Returns:
        Prometheus metrics in text format
    """
    from app.metrics import get_metrics

    return get_metrics()


@router.get("/ping")
async def ping() -> dict:
    """Simple ping endpoint for uptime monitoring.
    
    Returns:
        Ping response
    """
    return {"message": "pong"}
