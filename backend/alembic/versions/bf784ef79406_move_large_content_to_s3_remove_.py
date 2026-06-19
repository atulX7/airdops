"""move_large_content_to_s3_remove_deprecated_fields

Revision ID: bf784ef79406
Revises: d4dc74f12c9d
Create Date: 2026-01-23 11:36:09.954398

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'bf784ef79406'
down_revision = 'd4dc74f12c9d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. PipelineRun: Remove deprecated fields, make metrics_path required, make metrics nullable
    # Drop deprecated columns
    op.drop_column('pipeline_runs', 'stage_metrics')
    op.drop_column('pipeline_runs', 'aird_stages_completed')
    
    # Make metrics_path required (set default for existing rows first)
    op.execute("UPDATE pipeline_runs SET metrics_path = 'ws/' || workspace_id::text || '/prod/' || product_id::text || '/v/' || version::text || '/pipeline_runs/' || id::text || '/metrics.json' WHERE metrics_path IS NULL")
    op.alter_column('pipeline_runs', 'metrics_path', nullable=False, existing_type=sa.String(length=1000))
    
    # Make metrics nullable (it's now just a small summary)
    op.alter_column('pipeline_runs', 'metrics', nullable=True, existing_type=sa.JSON())
    
    # 2. CustomPlaybook: Replace yaml_content with yaml_content_path
    # Add new column
    op.add_column('custom_playbooks', sa.Column('yaml_content_path', sa.String(length=1000), nullable=True))
    
    # Migrate existing data: create S3 paths for existing yaml_content
    # Note: This assumes data will be migrated to S3 by application code before this migration
    # For now, set a placeholder path
    op.execute("UPDATE custom_playbooks SET yaml_content_path = 'ws/' || workspace_id::text || '/playbooks/' || id::text || '/content.yaml' WHERE yaml_content_path IS NULL")
    
    # Make yaml_content_path required
    op.alter_column('custom_playbooks', 'yaml_content_path', nullable=False, existing_type=sa.String(length=1000))
    
    # Drop old yaml_content column
    op.drop_column('custom_playbooks', 'yaml_content')
    
    # 3. EvalRun: Add trend_data_path, make metrics_path required
    op.add_column('eval_runs', sa.Column('trend_data_path', sa.String(length=1000), nullable=True))
    
    # Make metrics_path required (set default for existing rows)
    op.execute("UPDATE eval_runs SET metrics_path = 'ws/' || workspace_id::text || '/prod/' || product_id::text || '/v/' || version::text || '/eval/' || id::text || '/metrics.json' WHERE metrics_path IS NULL")
    op.alter_column('eval_runs', 'metrics_path', nullable=False, existing_type=sa.String(length=1000))
    
    # Make metrics nullable (it's now just a small summary)
    op.alter_column('eval_runs', 'metrics', nullable=True, existing_type=postgresql.JSONB(astext_type=sa.Text()))
    
    # Make trend_data nullable (it's now just a small summary)
    op.alter_column('eval_runs', 'trend_data', nullable=True, existing_type=postgresql.JSONB(astext_type=sa.Text()))
    
    # 4. EvalDatasetItem: Replace expected_answer with expected_answer_path
    op.add_column('eval_dataset_items', sa.Column('expected_answer_path', sa.String(length=1000), nullable=True))
    
    # Migrate existing data: create S3 paths for existing expected_answer
    op.execute("UPDATE eval_dataset_items SET expected_answer_path = 'ws/' || (SELECT workspace_id FROM eval_datasets WHERE eval_datasets.id = eval_dataset_items.dataset_id)::text || '/prod/' || (SELECT product_id FROM eval_datasets WHERE eval_datasets.id = eval_dataset_items.dataset_id)::text || '/eval_datasets/' || dataset_id::text || '/items/' || id::text || '/expected_answer.txt' WHERE expected_answer IS NOT NULL AND expected_answer_path IS NULL")
    
    # Drop old expected_answer column
    op.drop_column('eval_dataset_items', 'expected_answer')
    
    # 5. RAGRequestLog: Replace response with response_path
    op.add_column('rag_request_logs', sa.Column('response_path', sa.String(length=1000), nullable=True))
    
    # Migrate existing data: create S3 paths for existing response
    op.execute("UPDATE rag_request_logs SET response_path = 'ws/' || workspace_id::text || '/prod/' || product_id::text || '/v/' || version::text || '/rag_logs/' || id::text || '/response.txt' WHERE response IS NOT NULL AND response_path IS NULL")
    
    # Drop old response column
    op.drop_column('rag_request_logs', 'response')
    
    # 6. DataQualityComplianceReport: Add report_data_path, make it required
    op.add_column('data_quality_compliance_reports', sa.Column('report_data_path', sa.String(length=1000), nullable=True))
    
    # Migrate existing data: create S3 paths for existing report_data
    op.execute("UPDATE data_quality_compliance_reports SET report_data_path = 'ws/' || workspace_id::text || '/compliance/reports/' || id::text || '/report_data.json' WHERE report_data_path IS NULL")
    
    # Make report_data_path required
    op.alter_column('data_quality_compliance_reports', 'report_data_path', nullable=False, existing_type=sa.String(length=1000))
    
    # Make report_data nullable (it's now just a small summary)
    op.alter_column('data_quality_compliance_reports', 'report_data', nullable=True, existing_type=sa.JSON())


def downgrade() -> None:
    # Reverse all changes
    
    # 6. DataQualityComplianceReport: Restore report_data, drop report_data_path
    op.alter_column('data_quality_compliance_reports', 'report_data', nullable=False, existing_type=sa.JSON())
    op.drop_column('data_quality_compliance_reports', 'report_data_path')
    
    # 5. RAGRequestLog: Restore response, drop response_path
    op.add_column('rag_request_logs', sa.Column('response', sa.Text(), nullable=True))
    op.drop_column('rag_request_logs', 'response_path')
    
    # 4. EvalDatasetItem: Restore expected_answer, drop expected_answer_path
    op.add_column('eval_dataset_items', sa.Column('expected_answer', sa.Text(), nullable=True))
    op.drop_column('eval_dataset_items', 'expected_answer_path')
    
    # 3. EvalRun: Make metrics_path nullable, drop trend_data_path
    op.alter_column('eval_runs', 'metrics_path', nullable=True, existing_type=sa.String(length=1000))
    op.alter_column('eval_runs', 'metrics', nullable=True, existing_type=postgresql.JSONB(astext_type=sa.Text()))
    op.alter_column('eval_runs', 'trend_data', nullable=True, existing_type=postgresql.JSONB(astext_type=sa.Text()))
    op.drop_column('eval_runs', 'trend_data_path')
    
    # 2. CustomPlaybook: Restore yaml_content, drop yaml_content_path
    op.add_column('custom_playbooks', sa.Column('yaml_content', sa.Text(), nullable=True))
    op.drop_column('custom_playbooks', 'yaml_content_path')
    
    # 1. PipelineRun: Restore deprecated fields, make metrics_path nullable
    op.alter_column('pipeline_runs', 'metrics_path', nullable=True, existing_type=sa.String(length=1000))
    op.alter_column('pipeline_runs', 'metrics', nullable=False, server_default='{}', existing_type=sa.JSON())
    op.add_column('pipeline_runs', sa.Column('stage_metrics', sa.JSON(), nullable=True))
    op.add_column('pipeline_runs', sa.Column('aird_stages_completed', sa.JSON(), nullable=True))
