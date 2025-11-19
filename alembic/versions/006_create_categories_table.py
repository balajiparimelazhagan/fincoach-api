"""create categories table

Revision ID: 006
Revises: 005
Create Date: 2025-01-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'categories',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('label', sa.String(), nullable=False),
        sa.Column('picture', sa.String(), nullable=True),
    )
    op.create_index('ix_categories_id', 'categories', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_categories_id', table_name='categories')
    op.drop_table('categories')

