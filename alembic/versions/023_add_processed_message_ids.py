"""Add processed_message_ids column for idempotent email processing

Revision ID: 023
Revises: 022
Create Date: 2025-12-21 14:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = '023'
down_revision = '022'
branch_labels = None
depends_on = None


def upgrade():
    """
    Add processed_message_ids JSONB column to track which emails have been
    successfully processed. This enables:
    - Idempotent retries (skip already processed emails)
    - Accurate progress tracking (exact count)
    - Resume capability after crashes
    
    Structure: {"message_id_1": true, "message_id_2": true, ...}
    Set to null after job completion to save storage.
    """
    op.add_column(
        'email_transaction_sync_jobs',
        sa.Column('processed_message_ids', JSONB, nullable=True)
    )


def downgrade():
    """Remove processed_message_ids column"""
    op.drop_column('email_transaction_sync_jobs', 'processed_message_ids')
