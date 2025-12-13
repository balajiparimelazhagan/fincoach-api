"""create accounts table

Revision ID: 018
Revises: 017
Create Date: 2025-12-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '018'
down_revision: Union[str, None] = '017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'accounts',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('account_last_four', sa.String(4), nullable=False),
        sa.Column('bank_name', sa.String(), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    
    # Create foreign key constraint
    op.create_foreign_key(
        'fk_accounts_user_id',
        'accounts',
        'users',
        ['user_id'],
        ['id'],
        ondelete='CASCADE'
    )
    
    # Create indexes
    op.create_index('ix_accounts_id', 'accounts', ['id'], unique=False)
    op.create_index('ix_accounts_user_id', 'accounts', ['user_id'], unique=False)
    
    # Create unique constraint on user_id + account_last_four
    op.create_unique_constraint(
        'uq_accounts_user_account',
        'accounts',
        ['user_id', 'account_last_four']
    )


def downgrade() -> None:
    op.drop_constraint('uq_accounts_user_account', 'accounts', type_='unique')
    op.drop_index('ix_accounts_user_id', table_name='accounts')
    op.drop_index('ix_accounts_id', table_name='accounts')
    op.drop_constraint('fk_accounts_user_id', 'accounts', type_='foreignkey')
    op.drop_table('accounts')
