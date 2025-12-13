"""add type column to accounts table

Revision ID: 020
Revises: 019
Create Date: 2025-12-13 06:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '020'
down_revision = '019'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum type for account_type
    account_type_enum = sa.Enum('credit', 'savings', 'current', name='account_type_enum')
    account_type_enum.create(op.get_bind(), checkfirst=True)
    
    # Add type column with default 'savings'
    op.add_column('accounts', sa.Column('type', account_type_enum, nullable=False, server_default='savings'))


def downgrade() -> None:
    # Drop type column
    op.drop_column('accounts', 'type')
    
    # Drop enum type
    sa.Enum(name='account_type_enum').drop(op.get_bind(), checkfirst=True)
