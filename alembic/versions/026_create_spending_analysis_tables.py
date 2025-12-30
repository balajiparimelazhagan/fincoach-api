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
    # Create spending_analysis_jobs table
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
    
    # Create recurring_patterns table
    op.create_table(
        'recurring_patterns',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('transactor_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('direction', sa.String(), nullable=False),
        sa.Column('pattern_type', sa.String(), nullable=False),
        sa.Column('interval_days', sa.Integer(), nullable=False),
        sa.Column('amount_behavior', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='ACTIVE'),
        sa.Column('confidence', sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column('detected_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_evaluated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('detection_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['transactor_id'], ['transactors.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_recurring_patterns_user_id', 'recurring_patterns', ['user_id'], unique=False)
    op.create_index('uq_recurring_patterns_user_transactor_direction', 'recurring_patterns', ['user_id', 'transactor_id', 'direction'], unique=True)
    op.create_index('ix_recurring_patterns_user_status', 'recurring_patterns', ['user_id', 'status'], unique=False)
    op.create_index('ix_recurring_patterns_user_pattern_type', 'recurring_patterns', ['user_id', 'pattern_type'], unique=False)
    op.create_index('ix_recurring_patterns_user_transactor_direction', 'recurring_patterns', ['user_id', 'transactor_id', 'direction'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_recurring_patterns_user_transactor_direction', table_name='recurring_patterns')
    op.drop_index('ix_recurring_patterns_user_pattern_type', table_name='recurring_patterns')
    op.drop_index('ix_recurring_patterns_user_status', table_name='recurring_patterns')
    op.drop_index('uq_recurring_patterns_user_transactor_direction', table_name='recurring_patterns')
    op.drop_index('ix_recurring_patterns_user_id', table_name='recurring_patterns')
    op.drop_table('recurring_patterns')
    
    op.drop_index('ix_user_status_locked', table_name='spending_analysis_jobs')
    op.drop_index('ix_spending_analysis_jobs_is_locked', table_name='spending_analysis_jobs')
    op.drop_index('ix_spending_analysis_jobs_celery_task_id', table_name='spending_analysis_jobs')
    op.drop_index('ix_spending_analysis_jobs_status', table_name='spending_analysis_jobs')
    op.drop_index('ix_spending_analysis_jobs_user_id', table_name='spending_analysis_jobs')
    op.drop_table('spending_analysis_jobs')
