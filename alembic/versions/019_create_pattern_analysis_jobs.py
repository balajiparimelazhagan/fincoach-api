"""create pattern analysis jobs table

Revision ID: 019_create_pattern_analysis_jobs
Revises: 018_create_spending_patterns
Create Date: 2025-12-08

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision = '019_create_pattern_analysis_jobs'
down_revision = '018_create_spending_patterns'
branch_label = None
depends_on = None


def upgrade():
    # Create pattern_analysis_jobs table
    op.create_table(
        'pattern_analysis_jobs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('status', sa.Enum('pending', 'processing', 'completed', 'failed', name='pattern_job_status'), nullable=False, default='pending', index=True),
        
        # Analysis metrics
        sa.Column('total_transactors', sa.Integer(), default=0, nullable=False),
        sa.Column('processed_transactors', sa.Integer(), default=0, nullable=False),
        sa.Column('bill_patterns_found', sa.Integer(), default=0, nullable=False),
        sa.Column('recurring_patterns_found', sa.Integer(), default=0, nullable=False),
        sa.Column('total_patterns_found', sa.Integer(), default=0, nullable=False),
        sa.Column('duplicates_removed', sa.Integer(), default=0, nullable=False),
        
        # Progress tracking
        sa.Column('progress_percentage', sa.Float(), default=0.0, nullable=False),
        sa.Column('current_step', sa.String(), nullable=True),
        
        # Configuration
        sa.Column('force_reanalyze', sa.String(), default='false', nullable=False),
        sa.Column('min_occurrences', sa.Integer(), default=3, nullable=False),
        sa.Column('min_days_history', sa.Integer(), default=60, nullable=False),
        
        # Error tracking
        sa.Column('error_log', JSONB, default=[], nullable=False),
        sa.Column('error_message', sa.String(), nullable=True),
        
        # Timestamps
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False)
    )
    
    # Create additional index for created_at (user_id and status already indexed above)
    op.create_index('ix_pattern_analysis_jobs_created_at', 'pattern_analysis_jobs', ['created_at'])


def downgrade():
    op.drop_table('pattern_analysis_jobs')
    op.execute('DROP TYPE pattern_job_status')
