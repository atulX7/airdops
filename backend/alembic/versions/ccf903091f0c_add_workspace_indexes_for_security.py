"""add_workspace_indexes_for_security

Revision ID: ccf903091f0c
Revises: 008952e44f74
Create Date: 2025-12-30 11:45:12.247766

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


# revision identifiers, used by Alembic.
revision = 'ccf903091f0c'
down_revision = '008952e44f74'
branch_labels = None
depends_on = None


def index_exists(table_name, index_name):
    """Check if an index exists on a table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    indexes = inspector.get_indexes(table_name)
    return any(idx['name'] == index_name for idx in indexes)


def upgrade() -> None:
    """
    Add database index for workspace_members.user_id to improve security and query performance.
    
    This index is critical for allowed_workspaces() function performance, which is used
    extensively for user data separation and preventing data leakage between users.
    
    Note: Other workspace_id indexes (products, pipeline_runs, data_sources) already exist
    in the model definitions and were created by previous migrations, so we don't add them here.
    """
    # Index on workspace_members.user_id for fast user workspace membership lookups
    # This is critical for allowed_workspaces() function performance
    if not index_exists('workspace_members', 'idx_workspace_members_user_id'):
        op.create_index(
            'idx_workspace_members_user_id',
            'workspace_members',
            ['user_id'],
            unique=False
        )


def downgrade() -> None:
    """Remove the index added in upgrade."""
    if index_exists('workspace_members', 'idx_workspace_members_user_id'):
        op.drop_index('idx_workspace_members_user_id', table_name='workspace_members')
