"""add_rag_quality_metrics

Revision ID: 0fb4eacc78e6
Revises: 248c786dde45
Create Date: 2025-01-15 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect, text


# revision identifiers, used by Alembic.
revision = '0fb4eacc78e6'
down_revision = '248c786dde45'  # Changed from 'bda98fc65abe' to ensure eval_runs table exists first
branch_labels = None
depends_on = None


def table_exists(table_name):
    """Check if a table exists."""
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def enum_exists(enum_name):
    """Check if an enum type exists."""
    bind = op.get_bind()
    result = bind.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = :enum_name)"
    ), {"enum_name": enum_name})
    return result.scalar()


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    if not table_exists(table_name):
        return False
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    # Create EvalDatasetStatus enum if it doesn't exist
    # Check if enum already exists (it may have been created by be303e6b7efc)
    enum_already_exists = enum_exists('evaldatasetstatus')
    if not enum_already_exists:
        op.execute("CREATE TYPE evaldatasetstatus AS ENUM ('draft', 'active', 'archived')")
    
    # Create eval_datasets table if it doesn't exist
    if not table_exists('eval_datasets'):
        # Always use create_type=False since we handle enum creation manually above
        # This prevents SQLAlchemy from trying to create the enum type again
        status_enum = postgresql.ENUM('draft', 'active', 'archived', name='evaldatasetstatus', create_type=False)
        op.create_table(
        'eval_datasets',
        sa.Column('id', postgresql.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('workspace_id', postgresql.UUID(), nullable=False),
        sa.Column('product_id', postgresql.UUID(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('dataset_type', sa.String(50), nullable=False),
        sa.Column('version', sa.Integer(), nullable=True),
        sa.Column('status', status_enum, nullable=False, server_default='draft'),
        sa.Column('extra_metadata', postgresql.JSON(), nullable=True, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
        # Create indexes for eval_datasets
        op.create_index('idx_eval_datasets_product', 'eval_datasets', ['product_id'])
        op.create_index('idx_eval_datasets_workspace', 'eval_datasets', ['workspace_id'])
        op.create_index('idx_eval_datasets_type', 'eval_datasets', ['dataset_type'])
        op.create_index('idx_eval_datasets_status', 'eval_datasets', ['status'])
    
    # Create eval_dataset_items table if it doesn't exist
    if not table_exists('eval_dataset_items'):
        op.create_table(
        'eval_dataset_items',
        sa.Column('id', postgresql.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('dataset_id', postgresql.UUID(), nullable=False),
        sa.Column('query', sa.Text(), nullable=False),
        sa.Column('expected_answer', sa.Text(), nullable=True),
        sa.Column('expected_chunks', postgresql.JSON(), nullable=True),
        sa.Column('expected_docs', postgresql.JSON(), nullable=True),
        sa.Column('question_type', sa.String(50), nullable=True),
        sa.Column('extra_metadata', postgresql.JSON(), nullable=True, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['dataset_id'], ['eval_datasets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
        # Create index for eval_dataset_items
        op.create_index('idx_eval_dataset_items_dataset', 'eval_dataset_items', ['dataset_id'])
    
    # Extend eval_runs table with new fields (only if table exists and columns don't exist)
    if table_exists('eval_runs'):
        if not column_exists('eval_runs', 'dataset_id'):
            op.add_column('eval_runs', sa.Column('dataset_id', postgresql.UUID(), nullable=True))
        if not column_exists('eval_runs', 'report_path'):
            op.add_column('eval_runs', sa.Column('report_path', sa.String(1000), nullable=True))
        if not column_exists('eval_runs', 'trend_data'):
            op.add_column('eval_runs', sa.Column('trend_data', postgresql.JSONB(), nullable=True))
    
    # Create foreign key and indexes if they don't exist
    bind = op.get_bind()
    inspector = inspect(bind)
    if table_exists('eval_runs') and column_exists('eval_runs', 'dataset_id'):
        # Check if foreign key exists
        fk_exists = False
        for fk in inspector.get_foreign_keys('eval_runs'):
            if fk['name'] == 'fk_eval_runs_dataset' or (fk['referred_table'] == 'eval_datasets' and 'dataset_id' in fk['constrained_columns']):
                fk_exists = True
                break
        if not fk_exists:
            op.create_foreign_key('fk_eval_runs_dataset', 'eval_runs', 'eval_datasets', ['dataset_id'], ['id'], ondelete='SET NULL')
        
        # Check if indexes exist
        existing_indexes = [idx['name'] for idx in inspector.get_indexes('eval_runs')]
        if 'idx_eval_runs_dataset' not in existing_indexes:
            op.create_index('idx_eval_runs_dataset', 'eval_runs', ['dataset_id'])
        if 'idx_eval_runs_status' not in existing_indexes:
            op.create_index('idx_eval_runs_status', 'eval_runs', ['status'])
    
    # Create rag_request_logs table if it doesn't exist
    if not table_exists('rag_request_logs'):
        op.create_table(
        'rag_request_logs',
        sa.Column('id', postgresql.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('workspace_id', postgresql.UUID(), nullable=False),
        sa.Column('product_id', postgresql.UUID(), nullable=False),
        sa.Column('user_id', postgresql.UUID(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('query', sa.Text(), nullable=False),
        sa.Column('policy_context', postgresql.JSON(), nullable=True),
        sa.Column('acl_applied', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('acl_denied', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('retrieved_chunk_ids', postgresql.JSON(), nullable=True),
        sa.Column('retrieved_doc_ids', postgresql.JSON(), nullable=True),
        sa.Column('retrieval_scores', postgresql.JSON(), nullable=True),
        sa.Column('filters_applied', postgresql.JSON(), nullable=True),
        sa.Column('prompt_hash', sa.String(64), nullable=True),
        sa.Column('model', sa.String(100), nullable=True),
        sa.Column('temperature', sa.Float(), nullable=True),
        sa.Column('max_tokens', sa.Integer(), nullable=True),
        sa.Column('response', sa.Text(), nullable=True),
        sa.Column('response_tokens', sa.Integer(), nullable=True),
        sa.Column('latency_ms', sa.Float(), nullable=True),
        sa.Column('sampled_for_eval', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    
        # Create indexes for rag_request_logs
        op.create_index('idx_rag_logs_product_version', 'rag_request_logs', ['product_id', 'version'])
        op.create_index('idx_rag_logs_workspace', 'rag_request_logs', ['workspace_id'])
        op.create_index('idx_rag_logs_timestamp', 'rag_request_logs', ['timestamp'])
        op.create_index('idx_rag_logs_sampled', 'rag_request_logs', ['sampled_for_eval'])
    
    # Create rag_quality_metrics table if it doesn't exist
    if not table_exists('rag_quality_metrics'):
        op.create_table(
        'rag_quality_metrics',
        sa.Column('id', postgresql.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('workspace_id', postgresql.UUID(), nullable=False),
        sa.Column('product_id', postgresql.UUID(), nullable=False),
        sa.Column('eval_run_id', postgresql.UUID(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('metric_name', sa.String(100), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('threshold', sa.Float(), nullable=True),
        sa.Column('passed', sa.Boolean(), nullable=False),
        sa.Column('extra_metadata', postgresql.JSON(), nullable=True, server_default='{}'),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['eval_run_id'], ['eval_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
        # Create indexes for rag_quality_metrics
        op.create_index('idx_rag_metrics_product_version', 'rag_quality_metrics', ['product_id', 'version'])
        op.create_index('idx_rag_metrics_eval_run', 'rag_quality_metrics', ['eval_run_id'])
        op.create_index('idx_rag_metrics_name_timestamp', 'rag_quality_metrics', ['metric_name', 'timestamp'])
    
    # Add rag_quality_thresholds to products table if it doesn't exist
    if not column_exists('products', 'rag_quality_thresholds'):
        op.add_column('products', sa.Column('rag_quality_thresholds', postgresql.JSON(), nullable=True, server_default='{"groundedness_min": 0.80, "hallucination_rate_max": 0.05, "acl_leakage_max": 0.0, "citation_coverage_min": 0.90, "refusal_correctness_min": 0.95, "context_relevance_min": 0.75, "answer_relevance_min": 0.80}'))


def downgrade() -> None:
    # Remove rag_quality_thresholds from products
    op.drop_column('products', 'rag_quality_thresholds')
    
    # Drop rag_quality_metrics table
    op.drop_index('idx_rag_metrics_name_timestamp', table_name='rag_quality_metrics')
    op.drop_index('idx_rag_metrics_eval_run', table_name='rag_quality_metrics')
    op.drop_index('idx_rag_metrics_product_version', table_name='rag_quality_metrics')
    op.drop_table('rag_quality_metrics')
    
    # Drop rag_request_logs table
    op.drop_index('idx_rag_logs_sampled', table_name='rag_request_logs')
    op.drop_index('idx_rag_logs_timestamp', table_name='rag_request_logs')
    op.drop_index('idx_rag_logs_workspace', table_name='rag_request_logs')
    op.drop_index('idx_rag_logs_product_version', table_name='rag_request_logs')
    op.drop_table('rag_request_logs')
    
    # Remove extensions from eval_runs
    op.drop_index('idx_eval_runs_status', table_name='eval_runs')
    op.drop_index('idx_eval_runs_dataset', table_name='eval_runs')
    op.drop_constraint('fk_eval_runs_dataset', 'eval_runs', type_='foreignkey')
    op.drop_column('eval_runs', 'trend_data')
    op.drop_column('eval_runs', 'report_path')
    op.drop_column('eval_runs', 'dataset_id')
    
    # Drop eval_dataset_items table
    op.drop_index('idx_eval_dataset_items_dataset', table_name='eval_dataset_items')
    op.drop_table('eval_dataset_items')
    
    # Drop eval_datasets table
    op.drop_index('idx_eval_datasets_status', table_name='eval_datasets')
    op.drop_index('idx_eval_datasets_type', table_name='eval_datasets')
    op.drop_index('idx_eval_datasets_workspace', table_name='eval_datasets')
    op.drop_index('idx_eval_datasets_product', table_name='eval_datasets')
    op.drop_table('eval_datasets')
    
    # Drop enum
    op.execute("DROP TYPE evaldatasetstatus")

