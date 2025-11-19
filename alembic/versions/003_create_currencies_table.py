"""create currencies table

Revision ID: 003
Revises: 002
Create Date: 2025-01-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'currencies',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('value', sa.String(), nullable=False),  # Currency code (e.g., USD, EUR)
        sa.Column('country', sa.String(), nullable=False),
    )
    op.create_index('ix_currencies_id', 'currencies', ['id'], unique=False)
    op.create_index('ix_currencies_value', 'currencies', ['value'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_currencies_value', table_name='currencies')
    op.drop_index('ix_currencies_id', table_name='currencies')
    op.drop_table('currencies')

