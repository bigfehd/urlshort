"""FastAPI application factory and configuration."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
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

    # Custom exception handlers
    @app.exception_handler(HTTPException)
    async def custom_http_exception_handler(request: Request, exc: HTTPException):
        """Custom HTTP exception handler with 404 page support.
        
        Returns an HTML page for 404 errors, JSON for others.
        """
        if exc.status_code == 404:
            # Custom 404 HTML page
            return HTMLResponse(
                status_code=404,
                content="""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>404 - URL Not Found</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0;
            padding: 20px;
        }
        .container {
            background: white;
            border-radius: 10px;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
            padding: 40px 20px;
            text-align: center;
            max-width: 600px;
        }
        h1 {
            color: #764ba2;
            font-size: 48px;
            margin: 0 0 10px 0;
        }
        p {
            color: #666;
            font-size: 16px;
            line-height: 1.6;
            margin: 10px 0;
        }
        .error-code {
            color: #999;
            font-size: 14px;
            font-family: monospace;
            margin-top: 20px;
            padding: 10px;
            background: #f5f5f5;
            border-radius: 5px;
        }
        a {
            display: inline-block;
            margin-top: 20px;
            padding: 10px 30px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-decoration: none;
            border-radius: 5px;
            transition: transform 0.2s;
        }
        a:hover {
            transform: scale(1.05);
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>404</h1>
        <p><strong>Short URL Not Found</strong></p>
        <p>The link you're looking for doesn't exist or may have expired.</p>
        <p>Please check the URL and try again.</p>
        <div class="error-code">
            <small>Requested URL: """ + request.url.path + """</small>
        </div>
        <a href="/">← Go Home</a>
    </div>
</body>
</html>
                """,
            )
        else:
            # Return JSON for other HTTP errors
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "error": exc.detail or "Error",
                    "status_code": exc.status_code,
                },
            )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Global exception handler for unexpected errors."""
        logger.exception(f"Unhandled exception: {exc}")
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal Server Error",
                "status_code": 500,
                "path": str(request.url.path),
            },
        )

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
