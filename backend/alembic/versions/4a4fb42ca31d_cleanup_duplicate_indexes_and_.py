"""cleanup_duplicate_indexes_and_constraints

Revision ID: 4a4fb42ca31d
Revises: cde09da68630
Create Date: 2025-12-31 02:28:30.204755

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '4a4fb42ca31d'
down_revision = 'cde09da68630'
branch_labels = None
depends_on = None


def index_exists(table_name, index_name):
    """Check if an index exists on a table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    try:
        indexes = inspector.get_indexes(table_name)
        return any(idx['name'] == index_name for idx in indexes)
    except Exception:
        return False


def constraint_exists(table_name, constraint_name):
    """Check if a unique constraint exists on a table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    try:
        constraints = inspector.get_unique_constraints(table_name)
        return any(con['name'] == constraint_name for con in constraints)
    except Exception:
        # Fallback: check pg_constraint directly
        result = bind.execute(sa.text("""
            SELECT COUNT(*) 
            FROM pg_constraint 
            WHERE conrelid = :table_name::regclass 
            AND conname = :constraint_name
        """), {
            'table_name': table_name,
            'constraint_name': constraint_name
        })
        return result.scalar() > 0


def upgrade() -> None:
    """
    Clean up duplicate indexes and constraints.
    
    Removes:
    1. Duplicate index ix_workspaces_id (duplicate of primary key)
    2. Duplicate index ix_workspace_members_id (duplicate of primary key)
    3. Old unique constraint unique_workspace_user (replaced by ux_workspace_members_workspace_user)
    """
    
    # ============================================
    # 1. Remove duplicate index on workspaces
    # ============================================
    if index_exists('workspaces', 'ix_workspaces_id'):
        op.drop_index('ix_workspaces_id', table_name='workspaces')
    
    # ============================================
    # 2. Remove duplicate index on workspace_members
    # ============================================
    if index_exists('workspace_members', 'ix_workspace_members_id'):
        op.drop_index('ix_workspace_members_id', table_name='workspace_members')
    
    # ============================================
    # 3. Remove old unique constraint on workspace_members
    # ============================================
    # Check if the old constraint exists
    if constraint_exists('workspace_members', 'unique_workspace_user'):
        # Verify the new constraint exists before dropping the old one
        if constraint_exists('workspace_members', 'ux_workspace_members_workspace_user'):
            # Both exist, drop the old one
            op.drop_constraint('unique_workspace_user', 'workspace_members', type_='unique')
    elif index_exists('workspace_members', 'unique_workspace_user'):
        # If it's an index instead of a constraint, drop it
        op.drop_index('unique_workspace_user', table_name='workspace_members')


def downgrade() -> None:
    """
    Reverse the cleanup (restore duplicates if needed for rollback).
    Note: This is generally not recommended, but included for completeness.
    """
    
    # Restore duplicate indexes (not recommended, but possible)
    if not index_exists('workspaces', 'ix_workspaces_id'):
        op.create_index('ix_workspaces_id', 'workspaces', ['id'], unique=False)
    
    if not index_exists('workspace_members', 'ix_workspace_members_id'):
        op.create_index('ix_workspace_members_id', 'workspace_members', ['id'], unique=False)
    
    # Restore old unique constraint (only if new one exists)
    if constraint_exists('workspace_members', 'ux_workspace_members_workspace_user'):
        if not constraint_exists('workspace_members', 'unique_workspace_user'):
            op.create_unique_constraint('unique_workspace_user', 'workspace_members', ['workspace_id', 'user_id'])
