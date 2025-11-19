"""create budgets table

Revision ID: 009
Revises: 008
Create Date: 2025-01-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '009'
down_revision: Union[str, None] = '008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'budgets',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('date', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_budgets_id', 'budgets', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_budgets_id', table_name='budgets')
    op.drop_table('budgets')

