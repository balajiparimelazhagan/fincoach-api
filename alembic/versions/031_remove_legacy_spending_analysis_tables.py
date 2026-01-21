"""Remove legacy spending_analysis_jobs table

This migration removes the spending_analysis_jobs table from the old LLM-based system.

REMOVED:
- spending_analysis_jobs: Legacy job tracking (replaced by pattern discovery via API)

PRESERVED:
- recurring_patterns: Still used by new deterministic system
- recurring_pattern_streaks: Currently still used by pattern_service.py
  (Will be removed in future migration after refactoring to use pattern_obligations)

Revision ID: 031
Revises: 030
Create Date: 2026-01-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '031'
down_revision = '030'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Remove spending_analysis_jobs table only.
    
    This table was part of the old LLM-based pattern detection system
    and is completely replaced by the new deterministic pattern API.
    
    Note: recurring_pattern_streaks is preserved for now as pattern_service.py
    still uses it. It will be removed in a future migration after refactoring
    to use pattern_obligations for state tracking.
    """
    
    # Drop spending_analysis_jobs table (created in migration 026)
    # This table tracked LLM-based analysis jobs, no longer needed
    op.drop_index('ix_user_status_locked', table_name='spending_analysis_jobs', if_exists=True)
    op.drop_index('ix_spending_analysis_jobs_is_locked', table_name='spending_analysis_jobs', if_exists=True)
    op.drop_index('ix_spending_analysis_jobs_celery_task_id', table_name='spending_analysis_jobs', if_exists=True)
    op.drop_index('ix_spending_analysis_jobs_status', table_name='spending_analysis_jobs', if_exists=True)
    op.drop_index('ix_spending_analysis_jobs_user_id', table_name='spending_analysis_jobs', if_exists=True)
    op.drop_table('spending_analysis_jobs', if_exists=True)
    
    # Note: recurring_patterns and recurring_pattern_streaks tables are PRESERVED
    # - recurring_patterns: Used by new deterministic pattern system
    # - recurring_pattern_streaks: Still used by pattern_service.py (to be refactored)


def downgrade() -> None:
    """
    Recreate spending_analysis_jobs table (for rollback only).
    """
    
    # Recreate spending_analysis_jobs table
    op.create_table(
        'spending_analysis_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('transactor_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('direction', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('triggered_by', sa.String(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('error_log', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('celery_task_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_locked', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('celery_task_id'),
    )
    op.create_index('ix_spending_analysis_jobs_user_id', 'spending_analysis_jobs', ['user_id'], unique=False)
    op.create_index('ix_spending_analysis_jobs_status', 'spending_analysis_jobs', ['status'], unique=False)
    op.create_index('ix_spending_analysis_jobs_celery_task_id', 'spending_analysis_jobs', ['celery_task_id'], unique=False)
    op.create_index('ix_spending_analysis_jobs_is_locked', 'spending_analysis_jobs', ['is_locked'], unique=False)
    op.create_index('ix_user_status_locked', 'spending_analysis_jobs', ['user_id', 'status', 'is_locked'], unique=False)
