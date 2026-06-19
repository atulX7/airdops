"""make_metrics_path_nullable_in_eval_runs

Revision ID: 8de592097e5e
Revises: a1d98e6f62c0
Create Date: 2026-01-23 16:38:10.507868

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '8de592097e5e'
down_revision = 'a1d98e6f62c0'
branch_labels = None
depends_on = None


def is_column_nullable(table_name, column_name):
    """Check if a column is currently nullable."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = inspector.get_columns(table_name)
    for col in columns:
        if col['name'] == column_name:
            return col['nullable']
    return None


def upgrade() -> None:
    # Make metrics_path nullable in eval_runs
    # It's only set after evaluation completes, so it should be nullable when creating new runs
    # Check current state first - if already nullable, skip the alter
    if not is_column_nullable('eval_runs', 'metrics_path'):
        op.alter_column('eval_runs', 'metrics_path', nullable=True, existing_type=sa.String(length=1000))


def downgrade() -> None:
    # Revert to NOT NULL (set default for any NULL values first)
    op.execute("UPDATE eval_runs SET metrics_path = 'ws/' || workspace_id::text || '/prod/' || product_id::text || '/v/' || version::text || '/eval/' || id::text || '/metrics.json' WHERE metrics_path IS NULL")
    op.alter_column('eval_runs', 'metrics_path', nullable=False, existing_type=sa.String(length=1000))
