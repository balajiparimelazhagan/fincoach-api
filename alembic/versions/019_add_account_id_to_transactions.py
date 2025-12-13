"""add account_id to transactions table

Revision ID: 019
Revises: 018
Create Date: 2025-12-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '019'
down_revision: Union[str, None] = '018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add account_id column to transactions table
    op.add_column(
        'transactions',
        sa.Column('account_id', postgresql.UUID(as_uuid=False), nullable=True)
    )
    
    # Create foreign key constraint
    op.create_foreign_key(
        'fk_transactions_account_id',
        'transactions',
        'accounts',
        ['account_id'],
        ['id'],
        ondelete='SET NULL'
    )
    
    # Create index on account_id
    op.create_index('ix_transactions_account_id', 'transactions', ['account_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_transactions_account_id', table_name='transactions')
    op.drop_constraint('fk_transactions_account_id', 'transactions', type_='foreignkey')
    op.drop_column('transactions', 'account_id')
