"""Pydantic schemas for request/response validation."""
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, HttpUrl, field_validator


class CreateShortURLRequest(BaseModel):
    """Request schema for creating a shortened URL."""

    original_url: HttpUrl
    description: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "original_url": "https://www.example.com/very/long/url",
                    "description": "Example long URL",
                }
            ]
        }
    }

    @field_validator("original_url", mode="before")
    @classmethod
    def validate_url_length(cls, v: str) -> str:
        """Validate URL length (max 2000 characters)."""
        if len(str(v)) > 2000:
            raise ValueError("URL cannot exceed 2000 characters")
        return v

    @field_validator("original_url", mode="after")
    @classmethod
    def validate_no_private_ips(cls, v: HttpUrl) -> HttpUrl:
        """Block URLs pointing to private IP ranges."""
        url_str = str(v)
        parsed = urlparse(url_str)
        hostname = parsed.hostname or ""

        # Lowercase for comparison
        hostname_lower = hostname.lower()

        # Block localhost
        if hostname_lower in ["localhost", "127.0.0.1", "::1", "0.0.0.0"]:
            raise ValueError("Private loopback addresses are not allowed")

        # Block private IP ranges
        if hostname_lower.startswith("192.168.") or hostname_lower.startswith("10."):
            raise ValueError("Private IP addresses (192.168.x.x, 10.x.x.x) are not allowed")

        # Block 172.16.0.0 - 172.31.255.255
        if hostname_lower.startswith("172."):
            try:
                parts = hostname_lower.split(".")
                if len(parts) >= 2:
                    second_octet = int(parts[1])
                    if 16 <= second_octet <= 31:
                        raise ValueError(
                            "Private IP addresses (172.16.x.x - 172.31.x.x) are not allowed"
                        )
            except (ValueError, IndexError):
                pass  # Not a numeric IP, let it through

        return v


class ShortURLResponse(BaseModel):
    """Response schema for a shortened URL."""

    id: int
    short_code: str
    original_url: str
    description: Optional[str]
    short_url: str
    click_count: int
    created_at: datetime
    updated_at: datetime
    last_accessed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class CreateShortURLResponse(BaseModel):
    """Response schema for URL creation."""

    short_code: str
    short_url: str
    original_url: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "short_code": "abc123",
                    "short_url": "http://localhost:8000/abc123",
                    "original_url": "https://www.example.com/very/long/url",
                }
            ]
        }
    }


class ClickEventResponse(BaseModel):
    """Response schema for a click event."""

    id: int
    short_url_id: int
    clicked_at: datetime
    user_agent: Optional[str]
    referrer: Optional[str]
    ip_address: Optional[str]
    device_type: str

    model_config = {"from_attributes": True}


class AnalyticsDataPoint(BaseModel):
    """Single data point in analytics."""

    timestamp: datetime
    click_count: int


class AnalyticsResponse(BaseModel):
    """Response schema for analytics."""

    short_code: str
    original_url: str
    total_clicks: int
    created_at: datetime
    last_accessed_at: Optional[datetime]
    data_points: list[AnalyticsDataPoint]

    model_config = {"from_attributes": True}


class HealthResponse(BaseModel):
    """Response schema for health check."""

    status: str
    version: str
    database: str
    redis: str


class DeviceBreakdown(BaseModel):
    """Device type breakdown statistics."""

    desktop: int
    mobile: int
    bot: int


class TopURLItem(BaseModel):
    """Single item in top URLs list."""

    short_code: str
    original_url: str
    click_count: int
    device_breakdown: DeviceBreakdown


class TopURLsResponse(BaseModel):
    """Response for top URLs endpoint."""

    period: str
    returned_count: int
    top_urls: list[TopURLItem]


class HourlyDataPoint(BaseModel):
    """Single hour of analytics data."""

    timestamp: datetime
    hour: int
    clicks: int
    devices: DeviceBreakdown


class HourlyAnalyticsResponse(BaseModel):
    """Response for hourly analytics."""

    short_code: str
    period_days: int
    total_clicks: int
    hourly_data: list[HourlyDataPoint]


class DevicePercentage(BaseModel):
    """Device type with count and percentage."""

    count: int
    percentage: float


class DeviceAnalyticsResponse(BaseModel):
    """Response for device analytics."""

    short_code: str
    period_days: int
    total_clicks: int
    device_distribution: dict[str, DevicePercentage]


class ClicksPerMinuteResponse(BaseModel):
    """Response for clicks per minute endpoint."""

    period_seconds: int
    clicks_per_minute: int
    short_code: Optional[str] = None
    average_clicks_per_second: float
