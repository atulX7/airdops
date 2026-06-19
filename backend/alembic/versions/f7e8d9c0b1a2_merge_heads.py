"""merge_heads

Revision ID: f7e8d9c0b1a2
Revises: 8de592097e5e, b1c2d3e4f5a6
Create Date: 2026-02-15

Merges the two branch heads so 'alembic upgrade head' has a single target.
"""
from alembic import op
import sqlalchemy as sa


revision = "f7e8d9c0b1a2"
down_revision = ("8de592097e5e", "b1c2d3e4f5a6")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
