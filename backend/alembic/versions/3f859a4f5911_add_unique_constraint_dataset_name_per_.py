"""add_unique_constraint_dataset_name_per_product

Revision ID: 3f859a4f5911
Revises: cda8127f12b1
Create Date: 2026-01-22 11:52:05.742882

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = '3f859a4f5911'
down_revision = 'cda8127f12b1'
branch_labels = None
depends_on = None


def constraint_exists(table_name, constraint_name):
    """Check if a constraint exists."""
    bind = op.get_bind()
    result = bind.execute(
        text("SELECT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = :constraint_name)"),
        {"constraint_name": constraint_name}
    )
    return result.scalar()


def upgrade() -> None:
    # Add unique constraint on (product_id, name) if it doesn't exist
    if not constraint_exists('eval_datasets', 'unique_product_dataset_name'):
        op.create_unique_constraint('unique_product_dataset_name', 'eval_datasets', ['product_id', 'name'])


def downgrade() -> None:
    # Remove the unique constraint if it exists
    if constraint_exists('eval_datasets', 'unique_product_dataset_name'):
        op.drop_constraint('unique_product_dataset_name', 'eval_datasets', type_='unique')
