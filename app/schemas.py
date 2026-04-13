"""Pydantic schemas for request/response validation."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


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
