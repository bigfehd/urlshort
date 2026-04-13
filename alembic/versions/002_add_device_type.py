"""Add device_type column to click_events

Revision ID: 002_add_device_type
Revises: 001_initial
Create Date: 2024-01-15 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "002_add_device_type"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add device_type column to click_events."""
    op.add_column(
        "click_events",
        sa.Column("device_type", sa.String(length=20), nullable=False, server_default="desktop"),
    )


def downgrade() -> None:
    """Remove device_type column from click_events."""
    op.drop_column("click_events", "device_type")
