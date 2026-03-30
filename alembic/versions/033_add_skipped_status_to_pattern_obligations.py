"""Add SKIPPED status to pattern_obligations

Allows users to explicitly skip an obligation occurrence without marking
it as paid or missed. Skipped obligations are excluded from calculations.

Revision ID: 033
Revises: 032
Create Date: 2026-03-30 00:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '033'
down_revision = '032'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint('valid_obligation_status', 'pattern_obligations', type_='check')
    op.create_check_constraint(
        'valid_obligation_status',
        'pattern_obligations',
        "status IN ('EXPECTED', 'FULFILLED', 'MISSED', 'CANCELLED', 'SKIPPED')"
    )


def downgrade() -> None:
    op.drop_constraint('valid_obligation_status', 'pattern_obligations', type_='check')
    op.create_check_constraint(
        'valid_obligation_status',
        'pattern_obligations',
        "status IN ('EXPECTED', 'FULFILLED', 'MISSED', 'CANCELLED')"
    )