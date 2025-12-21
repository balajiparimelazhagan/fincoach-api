"""add monthly batching fields to email_transaction_sync_jobs

Revision ID: 022
Revises: 021
Create Date: 2025-12-20

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '022'
down_revision = '021'
branch_labels = None
depends_on = None


def upgrade():
    """Add fields to support monthly batching for email sync jobs"""
    op.add_column('email_transaction_sync_jobs', sa.Column('is_initial', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('email_transaction_sync_jobs', sa.Column('month_start_date', sa.Date(), nullable=True))
    op.add_column('email_transaction_sync_jobs', sa.Column('month_end_date', sa.Date(), nullable=True))
    op.add_column('email_transaction_sync_jobs', sa.Column('month_sequence', sa.Integer(), nullable=True))


def downgrade():
    """Remove monthly batching fields"""
    op.drop_column('email_transaction_sync_jobs', 'month_sequence')
    op.drop_column('email_transaction_sync_jobs', 'month_end_date')
    op.drop_column('email_transaction_sync_jobs', 'month_start_date')
    op.drop_column('email_transaction_sync_jobs', 'is_initial')
