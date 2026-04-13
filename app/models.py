"""SQLAlchemy models for the URL shortener."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ShortURL(Base):
    """Model for shortened URLs."""

    __tablename__ = "short_urls"

    id: Mapped[int] = mapped_column(primary_key=True)
    short_code: Mapped[str] = mapped_column(
        String(10), index=True, unique=True, nullable=False
    )
    original_url: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    click_count: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_short_urls_created_at", "created_at"),
        Index("ix_short_urls_short_code", "short_code"),
    )

    def __repr__(self) -> str:
        return f"<ShortURL(id={self.id}, short_code={self.short_code})>"


class ClickEvent(Base):
    """Model for tracking click events."""

    __tablename__ = "click_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    short_url_id: Mapped[int] = mapped_column(
        index=True, nullable=False
    )  # Foreign key to ShortURL
    clicked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    referrer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)

    __table_args__ = (
        Index("ix_click_events_short_url_id", "short_url_id"),
        Index("ix_click_events_clicked_at", "clicked_at"),
        Index("ix_click_events_short_url_id_clicked_at", "short_url_id", "clicked_at"),
    )

    def __repr__(self) -> str:
        return f"<ClickEvent(id={self.id}, short_url_id={self.short_url_id})>"
