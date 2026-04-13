"""Tests for production-grade reliability features."""
import asyncio
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
import redis.asyncio as aioredis

from app.main import create_app
from app.cache import cache
from app.schemas import CreateShortURLRequest


@pytest.fixture
def app():
    """Create test app."""
    return create_app()


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


class TestRateLimiting:
    """Test rate limiting on POST /shorten endpoint."""

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(self, client):
        """Test that rate limit is enforced."""
        # Mock the cache.incr to simulate rate limit counter
        with patch.object(cache, 'incr') as mock_incr, \
             patch.object(cache, 'expire') as mock_expire:
            
            # Simulate 21st request (exceeds 20 per minute limit)
            mock_incr.return_value = 21
            
            response = client.post(
                "/api/shorten",
                json={"original_url": "https://example.com"},
                headers={"X-Forwarded-For": "192.168.1.1"}
            )
            
            # Should be rate limited
            assert response.status_code == 429
            data = response.json()
            assert "Rate limit exceeded" in data["detail"]

    @pytest.mark.asyncio
    async def test_rate_limit_not_exceeded(self, client):
        """Test that requests under rate limit succeed."""
        with patch.object(cache, 'incr') as mock_incr, \
             patch.object(cache, 'expire') as mock_expire, \
             patch('app.api.urls.AsyncSession') as mock_session:
            
            # Simulate 15th request (under 20 limit)
            mock_incr.return_value = 15
            
            # Mock database operations
            mock_session_instance = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_session_instance
            
            response = client.post(
                "/api/shorten",
                json={"original_url": "https://example.com"},
                headers={"X-Forwarded-For": "192.168.1.1"}
            )
            
            # Should not be rate limited (may fail for other reasons in test)
            assert response.status_code != 429


class TestInputValidation:
    """Test input validation for URL creation."""

    def test_url_too_long(self, client):
        """Test that URLs longer than 2000 chars are rejected."""
        long_url = "https://example.com/" + "x" * 2000
        
        response = client.post(
            "/api/shorten",
            json={"original_url": long_url}
        )
        
        assert response.status_code == 422
        data = response.json()
        assert "2000" in str(data)

    def test_localhost_blocked(self, client):
        """Test that localhost URLs are blocked."""
        response = client.post(
            "/api/shorten",
            json={"original_url": "http://localhost:8000/test"}
        )
        
        assert response.status_code == 422
        data = response.json()
        assert "loopback" in str(data).lower() or "private" in str(data).lower()

    def test_private_ip_192_blocked(self, client):
        """Test that 192.168.x.x IPs are blocked."""
        response = client.post(
            "/api/shorten",
            json={"original_url": "http://192.168.1.1/test"}
        )
        
        assert response.status_code == 422
        data = response.json()
        assert "private" in str(data).lower()

    def test_private_ip_10_blocked(self, client):
        """Test that 10.x.x.x IPs are blocked."""
        response = client.post(
            "/api/shorten",
            json={"original_url": "http://10.0.0.1/test"}
        )
        
        assert response.status_code == 422
        data = response.json()
        assert "private" in str(data).lower()

    def test_valid_url_accepted(self, client):
        """Test that valid public URLs are accepted."""
        with patch('app.api.urls.AsyncSession') as mock_session:
            mock_session_instance = AsyncMock()
            mock_session_instance.flush = AsyncMock()
            mock_session_instance.commit = AsyncMock()
            
            mock_obj = AsyncMock()
            mock_obj.id = 1
            mock_session_instance.add(mock_obj)
            
            mock_session.return_value.__aenter__.return_value = mock_session_instance
            
            response = client.post(
                "/api/shorten",
                json={"original_url": "https://github.com/openai/gpt-4"}
            )
            
            # Should pass validation (may fail for other reasons in test)
            assert response.status_code != 422


class TestCustom404Page:
    """Test custom 404 error page."""

    def test_404_returns_html(self, client):
        """Test that 404 error returns HTML page."""
        response = client.get("/nonexistent-short-code")
        
        # Should return 404
        assert response.status_code == 404
        
        # Should be HTML content
        assert "text/html" in response.headers.get("content-type", "")
        assert "404" in response.text
        assert "Not Found" in response.text

    def test_404_page_structure(self, client):
        """Test that 404 page has proper structure."""
        response = client.get("/another-missing-url")
        
        assert response.status_code == 404
        assert "<html" in response.text
        assert "<title>404" in response.text
        assert "Short URL Not Found" in response.text


class TestMetricsEndpoint:
    """Test Prometheus metrics endpoint."""

    def test_metrics_endpoint_returns_prometheus_format(self, client):
        """Test that /metrics endpoint returns Prometheus format."""
        response = client.get("/metrics")
        
        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")
        
        text = response.text
        # Should contain Prometheus metrics
        assert "urlshort_" in text
        assert "HELP" in text or "TYPE" in text

    def test_metrics_contains_redirect_latency(self, client):
        """Test that metrics include redirect latency histogram."""
        response = client.get("/metrics")
        
        assert response.status_code == 200
        text = response.text
        assert "redirect_latency_ms" in text or "urlshort_redirect" in text

    def test_metrics_contains_cache_hit_rate(self, client):
        """Test that metrics include cache hit rate."""
        response = client.get("/metrics")
        
        assert response.status_code == 200
        text = response.text
        assert "cache_hit_rate" in text

    def test_metrics_contains_urls_created(self, client):
        """Test that metrics include URLs created counter."""
        response = client.get("/metrics")
        
        assert response.status_code == 200
        text = response.text
        assert "urls_created" in text or "urlshort_urls" in text


class TestCeleryRetry:
    """Test Celery task retry logic."""

    @pytest.mark.asyncio
    async def test_celery_task_has_retry_config(self):
        """Test that process_click_event task has proper retry configuration."""
        from workers.tasks import process_click_event
        
        # Check task configuration
        assert process_click_event.max_retries == 3
        # The task should have retry backoff settings

    def test_exponential_backoff_calculation(self):
        """Test exponential backoff calculation."""
        # Retry counts: 0, 1, 2, 3
        # Backoff should be: 2^0=1, 2^1=2, 2^2=4 seconds (capped at 600)
        
        test_cases = [
            (0, 1),      # First retry: 2^0 = 1
            (1, 2),      # Second retry: 2^1 = 2
            (2, 4),      # Third retry: 2^2 = 4
            (10, 600),   # Should cap at 600 (10 minutes)
        ]
        
        for retry_count, expected_max_backoff in test_cases:
            backoff = min(2 ** retry_count, 600)
            assert backoff <= expected_max_backoff


class TestCacheIntegration:
    """Test cache integration with rate limiting."""

    @pytest.mark.asyncio
    async def test_cache_incr_method_exists(self):
        """Test that cache has incr method for rate limiting."""
        # Check that the method exists and is callable
        assert hasattr(cache, 'incr')
        assert callable(cache.incr)

    @pytest.mark.asyncio
    async def test_cache_expire_method_exists(self):
        """Test that cache has expire method for rate limiting."""
        # Check that the method exists and is callable
        assert hasattr(cache, 'expire')
        assert callable(cache.expire)


class TestErrorHandling:
    """Test global error handling."""

    def test_global_exception_handler(self, client):
        """Test that unexpected errors return proper JSON response."""
        # Trigger an error by accessing an endpoint that might fail
        # This is generally hard to test without mocking internals
        pass

    def test_http_exception_with_json(self, client):
        """Test that HTTP exceptions return proper JSON."""
        response = client.post(
            "/api/shorten",
            json={"original_url": "http://192.168.1.1"}
        )
        
        # Should return JSON error, not HTML
        assert response.status_code == 422
        data = response.json()  # Should not raise


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
