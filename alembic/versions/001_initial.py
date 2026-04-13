"""Initial migration - Create tables

Revision ID: 001_initial
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create initial tables."""
    # Create short_urls table
    op.create_table(
        "short_urls",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("short_code", sa.String(length=10), nullable=False),
        sa.Column("original_url", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("click_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("short_code"),
    )
    op.create_index("ix_short_urls_short_code", "short_urls", ["short_code"])
    op.create_index("ix_short_urls_created_at", "short_urls", ["created_at"])

    # Create click_events table
    op.create_table(
        "click_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("short_url_id", sa.Integer(), nullable=False),
        sa.Column(
            "clicked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("referrer", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["short_url_id"], ["short_urls.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_click_events_short_url_id", "click_events", ["short_url_id"])
    op.create_index("ix_click_events_clicked_at", "click_events", ["clicked_at"])
    op.create_index(
        "ix_click_events_short_url_id_clicked_at",
        "click_events",
        ["short_url_id", "clicked_at"],
    )


def downgrade() -> None:
    """Drop initial tables."""
    op.drop_index("ix_click_events_short_url_id_clicked_at", table_name="click_events")
    op.drop_index("ix_click_events_clicked_at", table_name="click_events")
    op.drop_index("ix_click_events_short_url_id", table_name="click_events")
    op.drop_table("click_events")

    op.drop_index("ix_short_urls_created_at", table_name="short_urls")
    op.drop_index("ix_short_urls_short_code", table_name="short_urls")
    op.drop_table("short_urls")
