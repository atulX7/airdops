"""add_extraction_type_to_products

Revision ID: b1c2d3e4f5a6
Revises: 471e61c5d2db
Create Date: 2026-02-10

Extraction type (digital_pdf | scanned_pdf | mixed) is set by preprocess;
it is not a content_type. Content type remains semantic (medical, academic, etc.).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "b1c2d3e4f5a6"
down_revision = "cda8127f12b1"  # chain after main head (check_model_sync) to avoid multiple heads
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    if not column_exists("products", "extraction_type"):
        op.add_column(
            "products",
            sa.Column("extraction_type", sa.String(30), nullable=True),
        )


def downgrade() -> None:
    if column_exists("products", "extraction_type"):
        op.drop_column("products", "extraction_type")
