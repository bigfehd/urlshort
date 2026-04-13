"""FastAPI application factory and configuration."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST

from app.api import analytics, health, urls
from app.cache import cache
from app.database import close_db, init_db
from app.metrics import PrometheusMiddleware
from config import get_settings, setup_logging

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown.
    
    Args:
        app: FastAPI application
        
    Yields:
        During startup/shutdown
    """
    # Startup
    logger.info("Starting up URL Shortener")
    setup_logging(settings.LOG_LEVEL)

    # Initialize database
    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

    # Connect to Redis
    try:
        await cache.connect()
        logger.info("Redis cache connected")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down URL Shortener")
    await close_db()
    await cache.disconnect()
    logger.info("Cleanup completed")


def create_app() -> FastAPI:
    """Create and configure FastAPI application.
    
    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title=settings.API_TITLE,
        description=settings.API_DESCRIPTION,
        version=settings.API_VERSION,
        lifespan=lifespan,
    )

    # Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add Prometheus middleware
    app.middleware("http")(PrometheusMiddleware(app))

    # Include routers
    app.include_router(urls.router)
    app.include_router(analytics.router)
    app.include_router(health.router)

    # Root endpoint
    @app.get("/")
    async def root() -> dict:
        """Root endpoint with API information.
        
        Returns:
            API information
        """
        return {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "docs": "/docs",
            "redoc": "/redoc",
        }

    logger.info(f"FastAPI application created - {settings.APP_NAME} {settings.APP_VERSION}")
    return app


# Create the application instance
app = create_app()
