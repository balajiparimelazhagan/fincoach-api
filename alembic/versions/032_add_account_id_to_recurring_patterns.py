"""Add account_id to recurring_patterns

Stores the account most commonly associated with a recurring pattern,
derived from its historical transactions during pattern discovery.

Revision ID: 032
Revises: 031
Create Date: 2026-03-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '032'
down_revision = '031'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'recurring_patterns',
        sa.Column('account_id', sa.String(), nullable=True)
    )
    op.create_foreign_key(
        'fk_recurring_patterns_account_id',
        'recurring_patterns', 'accounts',
        ['account_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_index('ix_recurring_patterns_account_id', 'recurring_patterns', ['account_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_recurring_patterns_account_id', table_name='recurring_patterns')
    op.drop_constraint('fk_recurring_patterns_account_id', 'recurring_patterns', type_='foreignkey')
    op.drop_column('recurring_patterns', 'account_id')
