"""add_collection_name_to_pipeline_runs

Revision ID: d4dc74f12c9d
Revises: 3f859a4f5911
Create Date: 2026-01-22 16:47:50.941641

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4dc74f12c9d'
down_revision = '3f859a4f5911'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add collection_name column to pipeline_runs table
    op.add_column('pipeline_runs', sa.Column('collection_name', sa.String(length=500), nullable=True))
    # Create index for faster lookups
    op.create_index('idx_pipeline_runs_collection_name', 'pipeline_runs', ['collection_name'])


def downgrade() -> None:
    # Drop index first
    op.drop_index('idx_pipeline_runs_collection_name', table_name='pipeline_runs')
    # Drop column
    op.drop_column('pipeline_runs', 'collection_name')
