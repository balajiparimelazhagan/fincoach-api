"""add processed to transactions

Revision ID: 014
Revises: 013
Create Date: 2025-11-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '014'
down_revision: Union[str, None] = '013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('transactions', sa.Column('processed', sa.Boolean(), server_default=sa.text('FALSE'), nullable=False))

def downgrade() -> None:
    op.drop_column('transactions', 'processed')
