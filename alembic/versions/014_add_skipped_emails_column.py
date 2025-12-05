"""add skipped_emails column to transaction_sync_jobs

Revision ID: 014
Revises: 013
Create Date: 2025-12-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '014'
down_revision: Union[str, None] = '013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add skipped_emails column for tracking emails filtered by intent classifier
    op.add_column(
        'transaction_sync_jobs',
        sa.Column('skipped_emails', sa.Integer(), nullable=False, server_default='0')
    )


def downgrade() -> None:
    # Remove skipped_emails column
    op.drop_column('transaction_sync_jobs', 'skipped_emails')
