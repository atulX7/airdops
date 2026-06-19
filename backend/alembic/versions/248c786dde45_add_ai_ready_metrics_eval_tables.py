"""add_ai_ready_metrics_eval_tables

Revision ID: 248c786dde45
Revises: 4a4fb42ca31d
Create Date: 2025-12-31 11:27:47.692110

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '248c786dde45'
down_revision = '4a4fb42ca31d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create eval_queries table for synthetic query generation
    op.create_table(
        'eval_queries',
        sa.Column('id', postgresql.UUID(), nullable=False),
        sa.Column('workspace_id', postgresql.UUID(), nullable=False),
        sa.Column('product_id', postgresql.UUID(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('chunk_id', sa.String(255), nullable=False),
        sa.Column('query', sa.Text(), nullable=False),
        sa.Column('expected_chunk_id', sa.String(255), nullable=False),
        sa.Column('query_style', sa.String(50), nullable=True),  # 'technical', 'academic', etc.
        sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for eval_queries
    op.create_index('idx_eval_queries_product_version', 'eval_queries', ['product_id', 'version'])
    op.create_index('idx_eval_queries_chunk', 'eval_queries', ['chunk_id'])
    
    # Create eval_runs table for tracking evaluation runs
    op.create_table(
        'eval_runs',
        sa.Column('id', postgresql.UUID(), nullable=False),
        sa.Column('workspace_id', postgresql.UUID(), nullable=False),
        sa.Column('product_id', postgresql.UUID(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('pipeline_run_id', postgresql.UUID(), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),  # 'pending', 'running', 'completed', 'failed'
        sa.Column('metrics', postgresql.JSONB(), nullable=True),  # Store Recall@k, MRR, etc.
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['pipeline_run_id'], ['pipeline_runs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for eval_runs
    op.create_index('idx_eval_runs_product_version', 'eval_runs', ['product_id', 'version'])


def downgrade() -> None:
    op.drop_index('idx_eval_runs_product_version', table_name='eval_runs')
    op.drop_table('eval_runs')
    op.drop_index('idx_eval_queries_chunk', table_name='eval_queries')
    op.drop_index('idx_eval_queries_product_version', table_name='eval_queries')
    op.drop_table('eval_queries')
