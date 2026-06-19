"""ensure_extraction_type_on_products

Revision ID: c4e5f6a7b8d0
Revises: 202603040041
Create Date: 2026-03-07

Idempotent migration: adds products.extraction_type if missing.
Safe for envs that only applied one branch (and never ran b1c2d3e4f5a6).
Pipeline runs 'alembic upgrade head' once; no manual steps per env.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "c4e5f6a7b8d0"
down_revision = "202603040041"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    if not _column_exists("products", "extraction_type"):
        op.add_column(
            "products",
            sa.Column("extraction_type", sa.String(30), nullable=True),
        )


def downgrade() -> None:
    if _column_exists("products", "extraction_type"):
        op.drop_column("products", "extraction_type")
