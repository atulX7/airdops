"""add_password_reset_token_fields

Revision ID: e566f8bb7e32
Revises: c3f2eeca3a86
Create Date: 2026-01-01 14:36:59.056967

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'e566f8bb7e32'
down_revision = 'c3f2eeca3a86'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    # Add password reset token fields to users table
    if not column_exists('users', 'password_reset_token'):
        op.add_column('users', sa.Column('password_reset_token', sa.String(length=255), nullable=True))
        # Create index on password_reset_token
        op.create_index(op.f('ix_users_password_reset_token'), 'users', ['password_reset_token'], unique=True)
    
    if not column_exists('users', 'password_reset_token_expires'):
        op.add_column('users', sa.Column('password_reset_token_expires', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # Remove password reset token fields
    if column_exists('users', 'password_reset_token'):
        op.drop_index(op.f('ix_users_password_reset_token'), table_name='users')
        op.drop_column('users', 'password_reset_token')
    
    if column_exists('users', 'password_reset_token_expires'):
        op.drop_column('users', 'password_reset_token_expires')
