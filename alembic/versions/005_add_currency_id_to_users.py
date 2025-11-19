"""add currency_id to users table

Revision ID: 005
Revises: 004
Create Date: 2025-01-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add currency_id column
    op.add_column('users', sa.Column('currency_id', postgresql.UUID(as_uuid=False), nullable=True))
    
    # Create foreign key constraint
    op.create_foreign_key(
        'fk_users_currency_id',
        'users',
        'currencies',
        ['currency_id'],
        ['id'],
        ondelete='SET NULL'
    )
    
    # Create index for better query performance
    op.create_index('ix_users_currency_id', 'users', ['currency_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_users_currency_id', table_name='users')
    op.drop_constraint('fk_users_currency_id', 'users', type_='foreignkey')
    op.drop_column('users', 'currency_id')

