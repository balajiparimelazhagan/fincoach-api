"""Remove monthly batching fields from email_transaction_sync_jobs

These columns supported the now-removed monthly-batched initial sync system
(create_monthly_sync_jobs / process_monthly_email_job). Initial sync now runs
as a single job using the same path as incremental sync.

Revision ID: 036
Revises: 035
Create Date: 2026-04-20 00:00:00.000000
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = '036'
down_revision = '035'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column('email_transaction_sync_jobs', 'start_date')
    op.drop_column('email_transaction_sync_jobs', 'end_date')
    op.drop_column('email_transaction_sync_jobs', 'batch_sequence')
    op.drop_column('email_transaction_sync_jobs', 'processed_message_ids')
    op.drop_column('email_transaction_sync_jobs', 'progress_percentage')


def downgrade() -> None:
    op.add_column('email_transaction_sync_jobs',
        sa.Column('progress_percentage', sa.Float(), nullable=False, server_default='0.0'))
    op.add_column('email_transaction_sync_jobs',
        sa.Column('processed_message_ids', postgresql.JSONB(), nullable=True))
    op.add_column('email_transaction_sync_jobs',
        sa.Column('batch_sequence', sa.Integer(), nullable=True))
    op.add_column('email_transaction_sync_jobs',
        sa.Column('end_date', sa.Date(), nullable=True))
    op.add_column('email_transaction_sync_jobs',
        sa.Column('start_date', sa.Date(), nullable=True))
