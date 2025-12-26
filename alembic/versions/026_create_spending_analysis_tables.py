"""Create spending_analysis_jobs and recurring_patterns tables

Revision ID: 026
Revises: 025
Create Date: 2025-12-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '026'
down_revision = '025'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create spending_analysis_jobs table (use create_type=False for enums that may already exist)
    op.create_table(
        'spending_analysis_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.Enum('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', name='spending_analysis_job_status', create_type=False), nullable=False),
        sa.Column('triggered_by', sa.Enum('SCHEDULED', 'MANUAL', name='spending_analysis_job_trigger', create_type=False), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('total_transactors_analyzed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('patterns_detected', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('job_duration_seconds', sa.Float(), nullable=True),
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
    
    # Create recurring_patterns table
    op.create_table(
        'recurring_patterns',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('transactor_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('pattern_type', sa.String(), nullable=False),
        sa.Column('frequency', sa.String(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('avg_amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('min_amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('max_amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('amount_variance_percent', sa.Float(), nullable=False),
        sa.Column('total_occurrences', sa.Integer(), nullable=False),
        sa.Column('occurrences_in_pattern', sa.Integer(), nullable=False),
        sa.Column('avg_day_of_period', sa.Integer(), nullable=True),
        sa.Column('day_variance_days', sa.Integer(), nullable=True),
        sa.Column('first_transaction_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_transaction_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('analyzed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['transactor_id'], ['transactors.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_recurring_patterns_user_id', 'recurring_patterns', ['user_id'], unique=False)
    op.create_index('ix_user_transactor', 'recurring_patterns', ['user_id', 'transactor_id'], unique=True)
    op.create_index('ix_user_pattern_type', 'recurring_patterns', ['user_id', 'pattern_type'], unique=False)
    op.create_index('ix_user_confidence', 'recurring_patterns', ['user_id', 'confidence'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_user_confidence', table_name='recurring_patterns')
    op.drop_index('ix_user_pattern_type', table_name='recurring_patterns')
    op.drop_index('ix_user_transactor', table_name='recurring_patterns')
    op.drop_index('ix_recurring_patterns_user_id', table_name='recurring_patterns')
    op.drop_table('recurring_patterns')
    
    op.drop_index('ix_user_status_locked', table_name='spending_analysis_jobs')
    op.drop_index('ix_spending_analysis_jobs_is_locked', table_name='spending_analysis_jobs')
    op.drop_index('ix_spending_analysis_jobs_celery_task_id', table_name='spending_analysis_jobs')
    op.drop_index('ix_spending_analysis_jobs_status', table_name='spending_analysis_jobs')
    op.drop_index('ix_spending_analysis_jobs_user_id', table_name='spending_analysis_jobs')
    op.drop_table('spending_analysis_jobs')
    
    # Do not drop enums here, as they may be used by other tables/migrations
    # sa.Enum('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', name='spending_analysis_job_status', create_type=False).drop(op.get_bind())
    # sa.Enum('SCHEDULED', 'MANUAL', name='spending_analysis_job_trigger', create_type=False).drop(op.get_bind())
