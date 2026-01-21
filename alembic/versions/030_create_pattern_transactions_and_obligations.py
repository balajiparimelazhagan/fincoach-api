"""Create pattern_transactions and pattern_obligations tables

These tables complete the deterministic pattern tracking system:
- pattern_transactions: explicit linking (prevents reassignment bugs)
- pattern_obligations: stateful obligation tracking (no history recomputation)

Revision ID: 030
Revises: 029
Create Date: 2026-01-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '030'
down_revision = '029'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create pattern_transactions table
    op.create_table(
        'pattern_transactions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.func.gen_random_uuid()),
        sa.Column('recurring_pattern_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('transaction_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('linked_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['recurring_pattern_id'], ['recurring_patterns.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('recurring_pattern_id', 'transaction_id', name='uq_pattern_transaction'),
    )
    op.create_index('ix_pattern_transactions_pattern_id', 'pattern_transactions', ['recurring_pattern_id'], unique=False)
    op.create_index('ix_pattern_transactions_transaction_id', 'pattern_transactions', ['transaction_id'], unique=False)
    
    # Create pattern_obligations table
    op.create_table(
        'pattern_obligations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.func.gen_random_uuid()),
        sa.Column('recurring_pattern_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('expected_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('tolerance_days', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('expected_min_amount', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('expected_max_amount', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='EXPECTED'),
        sa.Column('fulfilled_by_transaction_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('fulfilled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('days_early', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['recurring_pattern_id'], ['recurring_patterns.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['fulfilled_by_transaction_id'], ['transactions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("status IN ('EXPECTED', 'FULFILLED', 'MISSED', 'CANCELLED')", name='valid_obligation_status'),
    )
    op.create_index('ix_pattern_obligations_pattern_expected', 'pattern_obligations', ['recurring_pattern_id', 'expected_date'], unique=False)
    op.create_index('ix_pattern_obligations_status', 'pattern_obligations', ['status'], unique=False)
    op.create_index('ix_pattern_obligations_fulfilled_by', 'pattern_obligations', ['fulfilled_by_transaction_id'], unique=False)


def downgrade() -> None:
    # Drop pattern_obligations table
    op.drop_index('ix_pattern_obligations_fulfilled_by', table_name='pattern_obligations')
    op.drop_index('ix_pattern_obligations_status', table_name='pattern_obligations')
    op.drop_index('ix_pattern_obligations_pattern_expected', table_name='pattern_obligations')
    op.drop_table('pattern_obligations')
    
    # Drop pattern_transactions table
    op.drop_index('ix_pattern_transactions_transaction_id', table_name='pattern_transactions')
    op.drop_index('ix_pattern_transactions_pattern_id', table_name='pattern_transactions')
    op.drop_table('pattern_transactions')
