"""add_dataset_name_and_pipeline_version_to_eval_runs

Revision ID: a1d98e6f62c0
Revises: bf784ef79406
Create Date: 2026-01-23 12:29:07.782204

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1d98e6f62c0'
down_revision = 'bf784ef79406'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add dataset_name and pipeline_version columns to eval_runs table
    op.add_column('eval_runs', sa.Column('dataset_name', sa.String(length=255), nullable=True))
    op.add_column('eval_runs', sa.Column('pipeline_version', sa.Integer(), nullable=True))


def downgrade() -> None:
    # Drop columns
    op.drop_column('eval_runs', 'pipeline_version')
    op.drop_column('eval_runs', 'dataset_name')
