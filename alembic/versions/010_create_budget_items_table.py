"""create budget_items table

Revision ID: 010
Revises: 009
Create Date: 2025-01-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '010'
down_revision: Union[str, None] = '009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'budget_items',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('budget_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('label', sa.String(), nullable=False),
        sa.Column('category_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('transaction_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(), nullable=True),
    )
    
    # Create foreign key constraints
    op.create_foreign_key(
        'fk_budget_items_budget_id',
        'budget_items',
        'budgets',
        ['budget_id'],
        ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_budget_items_category_id',
        'budget_items',
        'categories',
        ['category_id'],
        ['id'],
        ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_budget_items_transaction_id',
        'budget_items',
        'transactions',
        ['transaction_id'],
        ['id'],
        ondelete='SET NULL'
    )
    
    # Create indexes
    op.create_index('ix_budget_items_id', 'budget_items', ['id'], unique=False)
    op.create_index('ix_budget_items_budget_id', 'budget_items', ['budget_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_budget_items_budget_id', table_name='budget_items')
    op.drop_index('ix_budget_items_id', table_name='budget_items')
    op.drop_constraint('fk_budget_items_transaction_id', 'budget_items', type_='foreignkey')
    op.drop_constraint('fk_budget_items_category_id', 'budget_items', type_='foreignkey')
    op.drop_constraint('fk_budget_items_budget_id', 'budget_items', type_='foreignkey')
    op.drop_table('budget_items')

