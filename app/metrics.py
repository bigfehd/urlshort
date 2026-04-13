"""Prometheus metrics middleware for FastAPI."""
import logging
import time
from typing import Callable

from fastapi import Request
from prometheus_client import Counter, Gauge, Histogram, Info, generate_latest

logger = logging.getLogger(__name__)

# Prometheus metrics
app_info = Info("urlshort_app", "URL Shortener Application Info")
app_info.info({"version": "1.0.0"})

request_count = Counter(
    "urlshort_requests_total",
    "Total requests",
    ["method", "endpoint", "status"],
)

request_duration = Histogram(
    "urlshort_request_duration_seconds",
    "Request duration in seconds",
    ["method", "endpoint"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Production-grade metrics
redirect_latency_histogram = Histogram(
    "urlshort_redirect_latency_ms",
    "Redirect endpoint latency in milliseconds",
    buckets=(1, 2, 5, 10, 25, 50, 100, 250, 500, 1000),
)

cache_hit_rate_gauge = Gauge(
    "urlshort_cache_hit_rate",
    "Cache hit rate (0-100)",
)

redirects_total = Counter(
    "urlshort_redirects_total",
    "Total redirect requests",
    ["short_code", "status"],
)

cache_hits = Counter(
    "urlshort_cache_hits_total",
    "Total cache hits",
)

cache_misses = Counter(
    "urlshort_cache_misses_total",
    "Total cache misses",
)

database_errors = Counter(
    "urlshort_database_errors_total",
    "Total database errors",
)

celery_tasks = Counter(
    "urlshort_celery_tasks_total",
    "Total Celery tasks",
    ["task_name", "status"],
)

urls_created_total = Counter(
    "urlshort_urls_created_total",
    "Total URLs created",
)


class PrometheusMiddleware:
    """Middleware to track HTTP metrics."""

    def __init__(self, app_instance: object) -> None:
        """Initialize middleware.
        
        Args:
            app_instance: FastAPI application instance
        """
        self.app = app_instance

    async def __call__(self, request: Request, call_next: Callable) -> object:
        """Process request and track metrics.
        
        Args:
            request: HTTP request
            call_next: Next middleware/handler
            
        Returns:
            HTTP response
        """
        start_time = time.time()
        
        # Get endpoint path (without query params)
        endpoint = request.url.path
        method = request.method

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            logger.error(f"Request failed: {e}")
            status_code = 500
            raise
        finally:
            duration = time.time() - start_time
            request_count.labels(method=method, endpoint=endpoint, status=status_code).inc()
            request_duration.labels(method=method, endpoint=endpoint).observe(duration)
            
            # Track redirect latency specifically
            if endpoint.startswith("/") and method == "GET" and status_code == 302:
                redirect_latency_histogram.observe(duration * 1000)  # Convert to ms

        return response


def get_metrics() -> bytes:
    """Get Prometheus metrics in text format.
    
    Returns:
        Metrics in Prometheus text format
    """
    # Update cache hit rate gauge
    try:
        total_hits = cache_hits._value.get()
        total_misses = cache_misses._value.get()
        total_requests = total_hits + total_misses
        if total_requests > 0:
            hit_rate = (total_hits / total_requests) * 100
            cache_hit_rate_gauge.set(hit_rate)
    except Exception:
        pass  # Silently ignore if metrics not available

    return generate_latest()
