"""add transaction_type to spend_analysis

Revision ID: 015
Revises: 014
Create Date: 2025-11-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '015'
down_revision: Union[str, None] = '014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add column with server_default 'expense' so existing rows (all expenses) populate.
    op.add_column('spend_analysis', sa.Column('transaction_type', sa.String(), nullable=False, server_default='expense'))
    # Create index for faster filtering by type combined with user/category.
    op.create_index('ix_spend_analysis_transaction_type', 'spend_analysis', ['transaction_type'], unique=False)

    # Optional: if future queries filter on (user_id, transaction_type) often, composite index can be added later.


def downgrade() -> None:
    op.drop_index('ix_spend_analysis_transaction_type', table_name='spend_analysis')
    op.drop_column('spend_analysis', 'transaction_type')
