"""Add paid_months to custom_budget_items for per-month paid tracking

Revision ID: 035
Revises: 034
Create Date: 2026-04-07 00:00:00.000000
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = '035'
down_revision = '034'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'custom_budget_items',
        sa.Column('paid_months', postgresql.JSONB, nullable=False, server_default='[]'),
    )


def downgrade() -> None:
    op.drop_column('custom_budget_items', 'paid_months')
