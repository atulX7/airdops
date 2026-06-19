"""add_settings_to_workspace

Revision ID: 471e61c5d2db
Revises: f3d3928ec4ad
Create Date: 2025-12-24 09:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '471e61c5d2db'
down_revision = 'f3777117c808'  # Changed to merge with the other head
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add settings column to workspaces table
    op.add_column('workspaces', sa.Column('settings', postgresql.JSON(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    # Remove settings column from workspaces table
    op.drop_column('workspaces', 'settings')
