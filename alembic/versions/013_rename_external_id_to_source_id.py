"""rename external_id to source_id in transactors table

Revision ID: 013
Revises: 012
Create Date: 2025-12-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '013'
down_revision: Union[str, None] = '012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename column from external_id to source_id
    op.alter_column(
        'transactors',
        'external_id',
        new_column_name='source_id',
        existing_type=sa.String(),
        existing_nullable=True
    )


def downgrade() -> None:
    # Rename column back from source_id to external_id
    op.alter_column(
        'transactors',
        'source_id',
        new_column_name='external_id',
        existing_type=sa.String(),
        existing_nullable=True
    )
