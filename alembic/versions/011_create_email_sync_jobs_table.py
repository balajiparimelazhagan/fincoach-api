"""create email_sync_jobs table

Revision ID: 011
Revises: 010
Create Date: 2024-11-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '011'
down_revision = '010'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'email_sync_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.Enum('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'PAUSED', name='jobstatus'), nullable=False),
        sa.Column('total_emails', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('processed_emails', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('parsed_transactions', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_emails', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('progress_percentage', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('error_log', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )
    
    # Create indexes
    op.create_index('ix_email_sync_jobs_user_id', 'email_sync_jobs', ['user_id'])
    op.create_index('ix_email_sync_jobs_status', 'email_sync_jobs', ['status'])


def downgrade():
    op.drop_index('ix_email_sync_jobs_status', table_name='email_sync_jobs')
    op.drop_index('ix_email_sync_jobs_user_id', table_name='email_sync_jobs')
    op.drop_table('email_sync_jobs')
    op.execute('DROP TYPE jobstatus')
