"""create sms_transaction_sync_jobs table

Revision ID: 016
Revises: 015
Create Date: 2025-12-06

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '016'
down_revision = '015'
branch_labels = None
depends_on = None


def upgrade():
    # Create sms_transaction_sync_jobs table (reusing existing jobstatus enum)
    op.create_table(
        'sms_transaction_sync_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.Enum('pending', 'processing', 'completed', 'failed', 'paused', name='jobstatus'), nullable=False, server_default='pending'),
        sa.Column('total_sms', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('processed_sms', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('parsed_transactions', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_sms', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('skipped_sms', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('progress_percentage', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('error_log', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )
    
    # Create indexes
    op.create_index('ix_sms_transaction_sync_jobs_user_id', 'sms_transaction_sync_jobs', ['user_id'])
    op.create_index('ix_sms_transaction_sync_jobs_status', 'sms_transaction_sync_jobs', ['status'])


def downgrade():
    # Drop indexes
    op.drop_index('ix_sms_transaction_sync_jobs_status', 'sms_transaction_sync_jobs')
    op.drop_index('ix_sms_transaction_sync_jobs_user_id', 'sms_transaction_sync_jobs')
    
    # Drop table
    op.drop_table('sms_transaction_sync_jobs')
