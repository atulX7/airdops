"""add_email_verification_fields

Revision ID: c3f2eeca3a86
Revises: 248c786dde45
Create Date: 2025-12-31 16:16:13.896793

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'c3f2eeca3a86'
down_revision = '248c786dde45'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    # Add email verification fields to users table
    if not column_exists('users', 'email_verified'):
        op.add_column('users', sa.Column('email_verified', sa.Boolean(), nullable=False, server_default='false'))
    
    if not column_exists('users', 'verification_token'):
        op.add_column('users', sa.Column('verification_token', sa.String(length=255), nullable=True))
        # Create index on verification_token
        op.create_index(op.f('ix_users_verification_token'), 'users', ['verification_token'], unique=True)
    
    if not column_exists('users', 'verification_token_expires'):
        op.add_column('users', sa.Column('verification_token_expires', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # Remove email verification fields
    if column_exists('users', 'verification_token'):
        op.drop_index(op.f('ix_users_verification_token'), table_name='users')
        op.drop_column('users', 'verification_token')
    
    if column_exists('users', 'verification_token_expires'):
        op.drop_column('users', 'verification_token_expires')
    
    if column_exists('users', 'email_verified'):
        op.drop_column('users', 'email_verified')
