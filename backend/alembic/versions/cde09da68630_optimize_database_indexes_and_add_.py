"""optimize_database_indexes_and_add_features

Revision ID: cde09da68630
Revises: 74751c186a1e
Create Date: 2025-12-31 02:13:19.152302

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'cde09da68630'
down_revision = '74751c186a1e'
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


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    try:
        columns = [col['name'] for col in inspector.get_columns(table_name)]
        return column_name in columns
    except Exception:
        return False


def upgrade() -> None:
    """
    Optimize database indexes and add essential features.
    
    Changes:
    1. Remove duplicate indexes in products table
    2. Add composite indexes for common query patterns
    3. Add workspace owner tracking
    4. Add soft delete support (columns)
    5. Add unique constraint on workspace_members
    """
    
    # ============================================
    # 1. Remove duplicate indexes in products
    # ============================================
    if index_exists('products', 'ix_products_id'):
        op.drop_index('ix_products_id', table_name='products')
    
    if index_exists('products', 'ix_products_workspace_id'):
        op.drop_index('ix_products_workspace_id', table_name='products')
    
    # ============================================
    # 2. Add composite indexes for common API query patterns
    # ============================================
    
    # Products: workspace + status (common filter)
    if not index_exists('products', 'idx_products_workspace_status'):
        op.create_index(
            'idx_products_workspace_status',
            'products',
            ['workspace_id', 'status'],
            unique=False
        )
    
    # Products: workspace + version (common filter)
    if not index_exists('products', 'idx_products_workspace_version'):
        op.create_index(
            'idx_products_workspace_version',
            'products',
            ['workspace_id', 'current_version'],
            unique=False
        )
    
    # Products: workspace + created_at (common sorting)
    if not index_exists('products', 'idx_products_workspace_created_at'):
        op.create_index(
            'idx_products_workspace_created_at',
            'products',
            ['workspace_id', sa.text('created_at DESC')],
            unique=False
        )
    
    # ============================================
    # 3. Workspace membership: unique constraint
    # ============================================
    # Note: idx_workspace_members_user_id was added in ccf903091f0c
    # Add unique constraint to prevent duplicate memberships
    if not index_exists('workspace_members', 'ux_workspace_members_workspace_user'):
        op.create_index(
            'ux_workspace_members_workspace_user',
            'workspace_members',
            ['workspace_id', 'user_id'],
            unique=True
        )
    
    # ============================================
    # 4. Workspace owner tracking
    # ============================================
    if not column_exists('workspaces', 'owner_id'):
        op.add_column(
            'workspaces',
            sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=True)
        )
        # Add foreign key constraint
        op.create_foreign_key(
            'workspaces_owner_id_fkey',
            'workspaces',
            'users',
            ['owner_id'],
            ['id']
        )
    
    # Add index on owner_id
    if not index_exists('workspaces', 'idx_workspaces_owner_id'):
        op.create_index(
            'idx_workspaces_owner_id',
            'workspaces',
            ['owner_id'],
            unique=False
        )
    
    # ============================================
    # 5. Soft delete support (add columns)
    # ============================================
    
    if not column_exists('products', 'deleted_at'):
        op.add_column(
            'products',
            sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True)
        )
    
    if not column_exists('users', 'deleted_at'):
        op.add_column(
            'users',
            sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True)
        )
    
    if not column_exists('workspaces', 'deleted_at'):
        op.add_column(
            'workspaces',
            sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True)
        )
    
    # ============================================
    # 6. Soft delete index for active products query
    # ============================================
    # This indexes the actual query pattern: "active products in workspace, sorted by created_at"
    if not index_exists('products', 'idx_products_workspace_active'):
        # Use raw SQL for partial index with WHERE clause
        op.execute("""
            CREATE INDEX idx_products_workspace_active
            ON products(workspace_id, created_at DESC)
            WHERE deleted_at IS NULL
        """)


def downgrade() -> None:
    """
    Reverse the changes made in upgrade().
    """
    
    # Remove soft delete index
    if index_exists('products', 'idx_products_workspace_active'):
        op.drop_index('idx_products_workspace_active', table_name='products')
    
    # Remove soft delete columns
    if column_exists('workspaces', 'deleted_at'):
        op.drop_column('workspaces', 'deleted_at')
    
    if column_exists('users', 'deleted_at'):
        op.drop_column('users', 'deleted_at')
    
    if column_exists('products', 'deleted_at'):
        op.drop_column('products', 'deleted_at')
    
    # Remove workspace owner tracking
    if index_exists('workspaces', 'idx_workspaces_owner_id'):
        op.drop_index('idx_workspaces_owner_id', table_name='workspaces')
    
    if column_exists('workspaces', 'owner_id'):
        op.drop_constraint('workspaces_owner_id_fkey', 'workspaces', type_='foreignkey')
        op.drop_column('workspaces', 'owner_id')
    
    # Remove unique constraint on workspace_members
    if index_exists('workspace_members', 'ux_workspace_members_workspace_user'):
        op.drop_index('ux_workspace_members_workspace_user', table_name='workspace_members')
    
    # Remove composite indexes
    if index_exists('products', 'idx_products_workspace_created_at'):
        op.drop_index('idx_products_workspace_created_at', table_name='products')
    
    if index_exists('products', 'idx_products_workspace_version'):
        op.drop_index('idx_products_workspace_version', table_name='products')
    
    if index_exists('products', 'idx_products_workspace_status'):
        op.drop_index('idx_products_workspace_status', table_name='products')
    
    # Restore duplicate indexes (if needed for rollback)
    # Note: We don't restore them by default as they're duplicates
    # Uncomment if you need them for backward compatibility
    # if not index_exists('products', 'ix_products_id'):
    #     op.create_index('ix_products_id', 'products', ['id'], unique=False)
    # if not index_exists('products', 'ix_products_workspace_id'):
    #     op.create_index('ix_products_workspace_id', 'products', ['workspace_id'], unique=False)
