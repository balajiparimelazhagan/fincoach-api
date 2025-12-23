"""improve email sync tracking

Revision ID: 025
Revises: 024
Create Date: 2024-12-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '025'
down_revision: Union[str, None] = '024'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename month_start_date and month_end_date to be more generic
    op.alter_column('email_transaction_sync_jobs', 'month_start_date',
                    new_column_name='start_date')
    op.alter_column('email_transaction_sync_jobs', 'month_end_date',
                    new_column_name='end_date')
    
    # Rename month_sequence to batch_sequence (more generic)
    op.alter_column('email_transaction_sync_jobs', 'month_sequence',
                    new_column_name='batch_sequence')


def downgrade() -> None:
    # Revert column renames
    op.alter_column('email_transaction_sync_jobs', 'batch_sequence',
                    new_column_name='month_sequence')
    op.alter_column('email_transaction_sync_jobs', 'end_date',
                    new_column_name='month_end_date')
    op.alter_column('email_transaction_sync_jobs', 'start_date',
                    new_column_name='month_start_date')
