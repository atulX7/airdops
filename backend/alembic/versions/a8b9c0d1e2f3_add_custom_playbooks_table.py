"""add_custom_playbooks_table

Revision ID: a8b9c0d1e2f3
Revises: df59fc2b6867
Create Date: 2025-12-25 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = 'a8b9c0d1e2f3'
down_revision = '471e61c5d2db'  # Points to latest migration head
branch_labels = None
depends_on = None


def table_exists(table_name):
    """Check if a table exists in the database."""
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    # Create custom_playbooks table
    if not table_exists('custom_playbooks'):
        op.create_table('custom_playbooks',
            sa.Column('id', UUID(as_uuid=True), nullable=False),
            sa.Column('workspace_id', UUID(as_uuid=True), nullable=False),
            sa.Column('owner_user_id', UUID(as_uuid=True), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('playbook_id', sa.String(length=100), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('yaml_content', sa.Text(), nullable=False),
            sa.Column('config', sa.JSON(), nullable=True),
            sa.Column('base_playbook_id', sa.String(length=50), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
            sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('workspace_id', 'playbook_id', name='unique_workspace_playbook_id')
        )
        
        # Create indexes
        op.create_index('idx_custom_playbooks_workspace_id', 'custom_playbooks', ['workspace_id'], unique=False)
        op.create_index('idx_custom_playbooks_owner_user_id', 'custom_playbooks', ['owner_user_id'], unique=False)
        op.create_index('idx_custom_playbooks_playbook_id', 'custom_playbooks', ['playbook_id'], unique=False)
        op.create_index(op.f('ix_custom_playbooks_id'), 'custom_playbooks', ['id'], unique=False)


def downgrade() -> None:
    # Drop indexes first
    op.drop_index(op.f('ix_custom_playbooks_id'), table_name='custom_playbooks')
    op.drop_index('idx_custom_playbooks_playbook_id', table_name='custom_playbooks')
    op.drop_index('idx_custom_playbooks_owner_user_id', table_name='custom_playbooks')
    op.drop_index('idx_custom_playbooks_workspace_id', table_name='custom_playbooks')
    
    # Drop table
    op.drop_table('custom_playbooks')

