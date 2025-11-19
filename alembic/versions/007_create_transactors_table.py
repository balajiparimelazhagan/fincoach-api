"""create transactors table

Revision ID: 007
Revises: 006
Create Date: 2025-01-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'transactors',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('external_id', sa.String(), nullable=True),
        sa.Column('picture', sa.String(), nullable=True),
    )
    
    # Create foreign key constraint
    op.create_foreign_key(
        'fk_transactors_user_id',
        'transactors',
        'users',
        ['user_id'],
        ['id'],
        ondelete='CASCADE'
    )
    
    # Create indexes
    op.create_index('ix_transactors_id', 'transactors', ['id'], unique=False)
    op.create_index('ix_transactors_user_id', 'transactors', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_transactors_user_id', table_name='transactors')
    op.drop_index('ix_transactors_id', table_name='transactors')
    op.drop_constraint('fk_transactors_user_id', 'transactors', type_='foreignkey')
    op.drop_table('transactors')

