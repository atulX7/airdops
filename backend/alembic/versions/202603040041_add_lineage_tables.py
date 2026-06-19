"""add lineage and dq finding tables

Revision ID: 202603040041
Revises: f7e8d9c0b1a2
Create Date: 2026-03-04 00:41:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '202603040041'
down_revision = 'f7e8d9c0b1a2'
branch_labels = None
depends_on = None


def _enum_exists(conn, name: str) -> bool:
    r = conn.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = :name"), {"name": name})
    return r.scalar() is not None


def _table_exists(conn, name: str) -> bool:
    r = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = :name"
        ),
        {"name": name},
    )
    return r.scalar() is not None


def upgrade() -> None:
    conn = op.get_bind()
    # Create enum types only if they do not exist (idempotent)
    if not _enum_exists(conn, 'lineagetype'):
        conn.execute(sa.text("CREATE TYPE lineagetype AS ENUM ('CHUNK', 'VECTOR', 'METADATA')"))
    if not _enum_exists(conn, 'ruleseverity'):
        conn.execute(sa.text("CREATE TYPE ruleseverity AS ENUM ('ERROR', 'WARNING', 'INFO')"))

    # Create tables only if they do not exist, using raw SQL so we use existing enum types
    # and never trigger SQLAlchemy's Enum.create() (which would error if type exists).
    if not _table_exists(conn, 'lineage_records'):
        conn.execute(sa.text("""
            CREATE TABLE lineage_records (
                id UUID PRIMARY KEY,
                workspace_id UUID NOT NULL REFERENCES workspaces(id),
                product_id UUID NOT NULL REFERENCES products(id),
                pipeline_run_id UUID REFERENCES pipeline_runs(id),
                raw_file_id UUID REFERENCES raw_files(id),
                version INTEGER NOT NULL DEFAULT 1,
                lineage_type lineagetype NOT NULL,
                chunk_id VARCHAR(500),
                vector_id VARCHAR(500),
                metadata_id VARCHAR(500),
                source_file VARCHAR(1000),
                page_start INTEGER,
                page_end INTEGER,
                transformation VARCHAR(255),
                transform_version VARCHAR(100),
                model_name VARCHAR(255),
                model_version VARCHAR(100),
                status VARCHAR(50),
                details JSONB,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                updated_at TIMESTAMP WITH TIME ZONE
            )
        """))
        op.create_index('idx_lineage_product_run_type', 'lineage_records', ['product_id', 'pipeline_run_id', 'lineage_type'])
        op.create_index('idx_lineage_chunk', 'lineage_records', ['chunk_id'])
        op.create_index('idx_lineage_vector', 'lineage_records', ['vector_id'])

    if not _table_exists(conn, 'data_quality_findings'):
        conn.execute(sa.text("""
            CREATE TABLE data_quality_findings (
                id UUID PRIMARY KEY,
                workspace_id UUID NOT NULL REFERENCES workspaces(id),
                product_id UUID NOT NULL REFERENCES products(id),
                pipeline_run_id UUID REFERENCES pipeline_runs(id),
                raw_file_id UUID REFERENCES raw_files(id),
                chunk_id VARCHAR(500),
                vector_id VARCHAR(500),
                rule_name VARCHAR(255) NOT NULL,
                severity ruleseverity NOT NULL DEFAULT 'WARNING',
                passed BOOLEAN NOT NULL DEFAULT true,
                details JSONB,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
            )
        """))
        op.create_index('idx_dq_findings_product_run', 'data_quality_findings', ['product_id', 'pipeline_run_id'])
        op.create_index('idx_dq_findings_chunk', 'data_quality_findings', ['chunk_id'])
        op.create_index('idx_dq_findings_vector', 'data_quality_findings', ['vector_id'])


def downgrade() -> None:
    conn = op.get_bind()
    if _table_exists(conn, 'data_quality_findings'):
        op.drop_index('idx_dq_findings_vector', table_name='data_quality_findings')
        op.drop_index('idx_dq_findings_chunk', table_name='data_quality_findings')
        op.drop_index('idx_dq_findings_product_run', table_name='data_quality_findings')
        op.drop_table('data_quality_findings')

    if _table_exists(conn, 'lineage_records'):
        op.drop_index('idx_lineage_vector', table_name='lineage_records')
        op.drop_index('idx_lineage_chunk', table_name='lineage_records')
        op.drop_index('idx_lineage_product_run_type', table_name='lineage_records')
        op.drop_table('lineage_records')

    if _enum_exists(conn, 'ruleseverity'):
        conn.execute(sa.text("DROP TYPE ruleseverity"))
    if _enum_exists(conn, 'lineagetype'):
        conn.execute(sa.text("DROP TYPE lineagetype"))
