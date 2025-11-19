"""create transactions table

Revision ID: 008
Revises: 007
Create Date: 2025-01-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '008'
down_revision: Union[str, None] = '007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'transactions',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('transaction_id', sa.String(), nullable=True),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('transactor_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('category_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('confidence', sa.String(), nullable=True),
        sa.Column('currency_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('message_id', sa.String(), nullable=True),
    )
    
    # Create foreign key constraints
    op.create_foreign_key(
        'fk_transactions_user_id',
        'transactions',
        'users',
        ['user_id'],
        ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_transactions_category_id',
        'transactions',
        'categories',
        ['category_id'],
        ['id'],
        ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_transactions_currency_id',
        'transactions',
        'currencies',
        ['currency_id'],
        ['id'],
        ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_transactions_transactor_id',
        'transactions',
        'transactors',
        ['transactor_id'],
        ['id'],
        ondelete='SET NULL'
    )
    
    # Create indexes
    op.create_index('ix_transactions_id', 'transactions', ['id'], unique=False)
    op.create_index('ix_transactions_user_id', 'transactions', ['user_id'], unique=False)
    op.create_index('ix_transactions_date', 'transactions', ['date'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_transactions_date', table_name='transactions')
    op.drop_index('ix_transactions_user_id', table_name='transactions')
    op.drop_index('ix_transactions_id', table_name='transactions')
    op.drop_constraint('fk_transactions_transactor_id', 'transactions', type_='foreignkey')
    op.drop_constraint('fk_transactions_currency_id', 'transactions', type_='foreignkey')
    op.drop_constraint('fk_transactions_category_id', 'transactions', type_='foreignkey')
    op.drop_constraint('fk_transactions_user_id', 'transactions', type_='foreignkey')
    op.drop_table('transactions')

