"""Redis cache layer for URL redirects."""
import json
import logging
import time
from typing import Any, Optional

import aioredis
from pydantic import HttpUrl

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class RedisCache:
    """Redis cache with cache-aside pattern for URL redirects."""

    def __init__(self, redis_url: str = settings.REDIS_URL):
        """Initialize Redis cache.
        
        Args:
            redis_url: Redis connection URL
        """
        self.redis_url = redis_url
        self.redis: Optional[aioredis.Redis] = None
        self.ttl = settings.REDIS_CACHE_TTL

    async def connect(self) -> None:
        """Connect to Redis."""
        try:
            self.redis = await aioredis.from_url(self.redis_url, decode_responses=True)
            # Test connection
            await self.redis.ping()
            logger.info("Connected to Redis")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self.redis:
            await self.redis.close()
            logger.info("Disconnected from Redis")

    async def get(self, key: str) -> Optional[str]:
        """Get value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found
        """
        if not self.redis:
            return None

        try:
            value = await self.redis.get(key)
            if value:
                logger.debug(f"Cache hit for key: {key}")
                return value
            logger.debug(f"Cache miss for key: {key}")
            return None
        except Exception as e:
            logger.warning(f"Cache get error for {key}: {e}")
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache (will be JSON-serialized)
            ttl: Time to live in seconds (uses default if None)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.redis:
            return False

        try:
            ttl = ttl or self.ttl
            # Serialize value to JSON
            serialized = (
                json.dumps(value) if not isinstance(value, str) else value
            )
            await self.redis.setex(key, ttl, serialized)
            logger.debug(f"Cache set for key: {key}")
            return True
        except Exception as e:
            logger.warning(f"Cache set error for {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete key from cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if successful, False otherwise
        """
        if not self.redis:
            return False

        try:
            await self.redis.delete(key)
            logger.debug(f"Cache delete for key: {key}")
            return True
        except Exception as e:
            logger.warning(f"Cache delete error for {key}: {e}")
            return False

    async def flush(self) -> bool:
        """Flush all keys from cache.
        
        Returns:
            True if successful, False otherwise
        """
        if not self.redis:
            return False

        try:
            await self.redis.flushdb()
            logger.info("Cache flushed")
            return True
        except Exception as e:
            logger.warning(f"Cache flush error: {e}")
            return False

    async def pipeline_get_and_enqueue(
        self, cache_key: str
    ) -> tuple[Optional[str], bool]:
        """Get cache value using pipelined operation.
        
        Args:
            cache_key: The cache key to retrieve
            
        Returns:
            Tuple of (cached_value, was_cached) where was_cached indicates cache hit
        """
        if not self.redis:
            return None, False

        try:
            pipe = self.redis.pipeline()
            pipe.get(cache_key)
            result = await pipe.execute()
            cached_value = result[0] if result else None
            was_cached = cached_value is not None
            return cached_value, was_cached
        except Exception as e:
            logger.warning(f"Pipeline get error for {cache_key}: {e}")
            return None, False

    async def pipeline_set(
        self, cache_key: str, value: str, ttl: Optional[int] = None
    ) -> bool:
        """Set cache value using pipelined operation.
        
        Args:
            cache_key: The cache key
            value: The value to cache
            ttl: Time to live in seconds
            
        Returns:
            True if successful, False otherwise
        """
        if not self.redis:
            return False

        try:
            ttl = ttl or self.ttl
            pipe = self.redis.pipeline()
            pipe.setex(cache_key, ttl, value)
            await pipe.execute()
            return True
        except Exception as e:
            logger.warning(f"Pipeline set error for {cache_key}: {e}")
            return False

    async def is_connected(self) -> bool:
        """Check if Redis is connected and healthy.
        
        Returns:
            True if connected and healthy, False otherwise
        """
        try:
            if self.redis:
                await self.redis.ping()
                return True
        except Exception as e:
            logger.warning(f"Redis health check failed: {e}")
        return False

    async def increment_sliding_window(
        self, key: str, window_seconds: int = 60
    ) -> int:
        """Increment a sliding window counter.
        
        Uses Redis sorted set to track timestamps within a window.
        Automatically removes old entries outside the window.
        
        Args:
            key: Redis key for the counter
            window_seconds: Time window in seconds
            
        Returns:
            Current count within the window
        """
        if not self.redis:
            return 0

        try:
            now = time.time()
            cutoff = now - window_seconds

            # Remove old entries
            await self.redis.zremrangebyscore(key, 0, cutoff)

            # Add current entry
            await self.redis.zadd(key, {str(now): now})

            # Set expiration on the key
            await self.redis.expire(key, window_seconds + 1)

            # Get current count
            count = await self.redis.zcard(key)
            logger.debug(f"Sliding window counter {key}: {count}")
            return count
        except Exception as e:
            logger.warning(f"Sliding window increment error for {key}: {e}")
            return 0

    async def get_sliding_window_count(self, key: str, window_seconds: int = 60) -> int:
        """Get current count in a sliding window.
        
        Args:
            key: Redis key for the counter
            window_seconds: Time window in seconds
            
        Returns:
            Current count within the window
        """
        if not self.redis:
            return 0

        try:
            now = time.time()
            cutoff = now - window_seconds

            # Remove old entries
            await self.redis.zremrangebyscore(key, 0, cutoff)

            # Get current count
            count = await self.redis.zcard(key)
            return count
        except Exception as e:
            logger.warning(f"Sliding window get error for {key}: {e}")
            return 0


# Global cache instance
cache = RedisCache()


def get_redirect_cache_key(short_code: str) -> str:
    """Get cache key for redirect."""
    return f"redirect:{short_code}"


def get_url_info_cache_key(short_code: str) -> str:
    """Get cache key for URL info."""
    return f"url_info:{short_code}"


class RedisUnavailableError(Exception):
    """Raised when Redis is unavailable and we're falling back to DB."""
    pass
