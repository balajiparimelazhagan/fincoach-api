"""rename transaction_sync_jobs to email_transaction_sync_jobs

Revision ID: 017
Revises: 016
Create Date: 2025-12-06

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '017'
down_revision = '016'
branch_labels = None
depends_on = None


def upgrade():
    # Rename the table
    op.rename_table('transaction_sync_jobs', 'email_transaction_sync_jobs')
    
    # Rename indexes
    op.execute('ALTER INDEX ix_transaction_sync_jobs_user_id RENAME TO ix_email_transaction_sync_jobs_user_id')
    op.execute('ALTER INDEX ix_transaction_sync_jobs_status RENAME TO ix_email_transaction_sync_jobs_status')


def downgrade():
    # Rename indexes back
    op.execute('ALTER INDEX ix_email_transaction_sync_jobs_status RENAME TO ix_transaction_sync_jobs_status')
    op.execute('ALTER INDEX ix_email_transaction_sync_jobs_user_id RENAME TO ix_transaction_sync_jobs_user_id')
    
    # Rename the table back
    op.rename_table('email_transaction_sync_jobs', 'transaction_sync_jobs')
