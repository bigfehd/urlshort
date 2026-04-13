"""API routes for health checks and system status."""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
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
        Health status with detailed component information
    """
    db_status = "unhealthy"
    redis_status = "unhealthy"

    # Check database connectivity
    try:
        await session.execute(text("SELECT 1"))
        db_status = "healthy"
        logger.debug("Database health check passed")
    except Exception as e:
        logger.error(f"Database health check failed: {e}")

    # Check Redis connectivity
    try:
        is_connected = await cache.is_connected()
        if is_connected:
            redis_status = "healthy"
            logger.debug("Redis health check passed")
        else:
            logger.warning("Redis health check returned false")
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")

    # Determine overall status
    overall_status = "healthy"
    if db_status == "unhealthy" or redis_status == "unhealthy":
        overall_status = "degraded"
    if db_status == "unhealthy":
        overall_status = "unhealthy"

    return HealthResponse(
        status=overall_status,
        version="1.0.0",
        database=db_status,
        redis=redis_status,
    )


@router.get("/health/detailed")
async def detailed_health(session: AsyncSession = Depends(get_db_session)) -> dict:
    """Detailed health check endpoint with components status.
    
    Provides granular status information for monitoring and debugging.
    
    Args:
        session: Database session
        
    Returns:
        Detailed health information including response times
    """
    import time

    health_info = {
        "timestamp": str(time.time()),
        "components": {
            "database": {"status": "unhealthy", "latency_ms": None},
            "redis": {"status": "unhealthy", "latency_ms": None},
        },
    }

    # Check database
    start = time.time()
    try:
        await session.execute(text("SELECT 1"))
        latency = round((time.time() - start) * 1000, 2)
        health_info["components"]["database"] = {
            "status": "healthy",
            "latency_ms": latency,
        }
    except Exception as e:
        health_info["components"]["database"]["error"] = str(e)

    # Check Redis
    start = time.time()
    try:
        is_connected = await cache.is_connected()
        latency = round((time.time() - start) * 1000, 2)
        status = "healthy" if is_connected else "unhealthy"
        health_info["components"]["redis"] = {
            "status": status,
            "latency_ms": latency,
        }
    except Exception as e:
        health_info["components"]["redis"]["error"] = str(e)

    # Determine overall status
    db_ok = health_info["components"]["database"]["status"] == "healthy"
    redis_ok = health_info["components"]["redis"]["status"] == "healthy"

    if db_ok and redis_ok:
        health_info["status"] = "healthy"
    elif db_ok or redis_ok:
        health_info["status"] = "degraded"
    else:
        health_info["status"] = "unhealthy"

    return health_info


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
