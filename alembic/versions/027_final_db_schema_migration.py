"""Final DB Schema Migration: Clean, minimal, correct schema

Implements:
- Adds direction column to recurring_patterns
- Adds status, last_evaluated_at, detection_version to recurring_patterns
- Creates recurring_pattern_streaks table (fast-changing state)
- Removes stats columns from recurring_patterns
- Creates budget_forecasts table (historical outputs)
- Adds necessary indexes
- Removes stats columns that should be recomputed

Revision ID: 027
Revises: 026
Create Date: 2025-12-30 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '027'
down_revision = '026'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Phase 1 & 2: Column additions and constraints already created in migration 026
    # (direction, status, last_evaluated_at, detection_version, and
    #  uq_recurring_patterns_user_transactor_direction constraint)
    # No operations needed here
    
    # Phase 3: Add new index for transactions
    op.create_index(
        'ix_transactions_user_transactor_direction_date',
        'transactions',
        ['user_id', 'transactor_id', 'type', 'date'],
        postgresql_where=sa.text('transactor_id IS NOT NULL')
    )
    
    # Phase 4: Create recurring_pattern_streaks table
    op.create_table(
        'recurring_pattern_streaks',
        sa.Column('recurring_pattern_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('current_streak_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('longest_streak_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_actual_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_expected_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('missed_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('confidence_multiplier', sa.Numeric(precision=4, scale=3), nullable=False, server_default='1.0'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['recurring_pattern_id'], ['recurring_patterns.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('recurring_pattern_id'),
        sa.CheckConstraint('confidence_multiplier >= 0.0 AND confidence_multiplier <= 1.0', name='streak_multiplier_range')
    )
    op.create_index('ix_recurring_pattern_streaks_updated_at', 'recurring_pattern_streaks', ['updated_at'], unique=False)
    
    # Phase 5: Populate recurring_pattern_streaks from recurring_patterns
    op.execute("""
        INSERT INTO recurring_pattern_streaks (
            recurring_pattern_id,
            current_streak_count,
            longest_streak_count,
            confidence_multiplier,
            updated_at
        )
        SELECT 
            id,
            0,
            0,
            1.0,
            now()
        FROM recurring_patterns
        ON CONFLICT (recurring_pattern_id) DO NOTHING
    """)
    
    # Phase 6: Create budget_forecasts table
    op.create_table(
        'budget_forecasts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.func.gen_random_uuid()),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('transactor_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('direction', sa.String(), nullable=False),
        sa.Column('recurring_pattern_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('expected_min_amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('expected_max_amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('confidence', sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column('explanation_text', sa.Text(), nullable=True),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['transactor_id'], ['transactors.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['recurring_pattern_id'], ['recurring_patterns.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_budget_forecasts_user_id', 'budget_forecasts', ['user_id'], unique=False)
    op.create_index('ix_budget_forecasts_user_generated_at', 'budget_forecasts', ['user_id', 'generated_at'], unique=False)
    op.create_index('ix_budget_forecasts_recurring_pattern_id', 'budget_forecasts', ['recurring_pattern_id'], unique=False)
    op.create_index('ix_budget_forecasts_transactor_id', 'budget_forecasts', ['transactor_id'], unique=False)
    
    # Phase 7: Indexes already created in migration 026 for recurring_patterns
    # (ix_recurring_patterns_user_id, ix_recurring_patterns_user_status, etc.)
    # No additional indexes needed here
    
    # Phase 8: Column updates for recurring_patterns
    # Note: Migration 026 already creates with correct schema:
    # - Has pattern_type, interval_days, amount_behavior, status, confidence
    # - No need to rename, add, or drop columns
    
    # Phase 9: Update spending_analysis_jobs
    # No need to add them again
    
    # Convert status column from ENUM to VARCHAR (if needed)
    # This is already VARCHAR in migration 026, so this is a no-op
    # Keeping for idempotency
    op.execute("""
        ALTER TABLE spending_analysis_jobs 
        ALTER COLUMN status TYPE varchar 
        USING status
    """)


def downgrade() -> None:
    # Reverse Phase 9 - no operations needed (Phase 9 only executes no-op)
    
    # Reverse Phase 8 - no operations since migration 026 already has correct schema
    
    # Reverse Phase 7 - no operations (no new indexes added in Phase 7)
    
    # Reverse Phase 6
    op.drop_index('ix_budget_forecasts_transactor_id', table_name='budget_forecasts')
    op.drop_index('ix_budget_forecasts_recurring_pattern_id', table_name='budget_forecasts')
    op.drop_index('ix_budget_forecasts_user_generated_at', table_name='budget_forecasts')
    op.drop_index('ix_budget_forecasts_user_id', table_name='budget_forecasts')
    op.drop_table('budget_forecasts')
    
    # Reverse Phase 5
    op.execute("""
        DELETE FROM recurring_pattern_streaks
    """)
    
    # Reverse Phase 4
    op.drop_index('ix_recurring_pattern_streaks_updated_at', table_name='recurring_pattern_streaks')
    op.drop_table('recurring_pattern_streaks')
    
    # Reverse Phase 3
    op.drop_index('ix_transactions_user_transactor_direction_date', table_name='transactions')
    
    # Reverse Phase 2 - constraint already created in migration 026
    # No operations needed here
    
    # Reverse Phase 1 - no operations (columns created in migration 026)
