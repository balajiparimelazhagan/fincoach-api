"""Add custom_budget_items table for user-defined monthly budget entries

Revision ID: 034
Revises: 033
Create Date: 2026-04-03 00:00:00.000000
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = '034'
down_revision = '033'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'custom_budget_items',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=False),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('label', sa.String(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('day_of_month', sa.Integer(), nullable=True),
        sa.Column('section', sa.String(), nullable=False, server_default='bills'),
        sa.Column('category_id', postgresql.UUID(as_uuid=False),
                  sa.ForeignKey('categories.id', ondelete='SET NULL'), nullable=True),
        sa.Column('transactor_id', postgresql.UUID(as_uuid=False),
                  sa.ForeignKey('transactors.id', ondelete='SET NULL'), nullable=True),
        sa.Column('account_id', postgresql.UUID(as_uuid=False),
                  sa.ForeignKey('accounts.id', ondelete='SET NULL'), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_custom_budget_items_user_id', 'custom_budget_items', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_custom_budget_items_user_id', table_name='custom_budget_items')
    op.drop_table('custom_budget_items')
