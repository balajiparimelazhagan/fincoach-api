"""add unique constraint on message_id

Revision ID: 012
Revises: 011
Create Date: 2024-11-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '012'
down_revision = '011'
branch_labels = None
depends_on = None


def upgrade():
    # Add unique constraint on message_id to prevent duplicate transaction processing
    # Check if constraint already exists before creating
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    
    constraints = [c['name'] for c in inspector.get_unique_constraints('transactions')]
    
    if 'uq_transactions_message_id' not in constraints:
        op.create_unique_constraint(
            'uq_transactions_message_id',
            'transactions',
            ['message_id']
        )


def downgrade():
    # Check if constraint exists before dropping
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    
    constraints = [c['name'] for c in inspector.get_unique_constraints('transactions')]
    
    if 'uq_transactions_message_id' in constraints:
        op.drop_constraint('uq_transactions_message_id', 'transactions', type_='unique')
