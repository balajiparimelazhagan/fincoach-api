"""create spending patterns tables

Revision ID: 018_create_spending_patterns
Revises: 017_rename_to_email_transaction_sync_jobs
Create Date: 2025-12-07

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = '018_create_spending_patterns'
down_revision = '017'
branch_label = None
depends_on = None


def upgrade():
    # Create spending_patterns table
    op.create_table(
        'spending_patterns',
        sa.Column('id', UUID(as_uuid=False), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=False), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('transactor_id', UUID(as_uuid=False), sa.ForeignKey('transactors.id', ondelete='SET NULL'), nullable=True),
        sa.Column('category_id', UUID(as_uuid=False), sa.ForeignKey('categories.id', ondelete='SET NULL'), nullable=True),
        
        # Pattern Classification
        sa.Column('pattern_type', sa.String(), nullable=False),
        sa.Column('pattern_name', sa.String(), nullable=True),
        
        # Frequency Detection
        sa.Column('frequency_days', sa.Integer(), nullable=True),
        sa.Column('frequency_label', sa.String(), nullable=True),
        sa.Column('frequency_variance_days', sa.Integer(), nullable=True),
        
        # Amount Analysis
        sa.Column('average_amount', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('min_amount', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('max_amount', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('amount_variance_percentage', sa.Numeric(precision=5, scale=2), nullable=True),
        
        # Prediction
        sa.Column('last_transaction_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_expected_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expected_amount', sa.Numeric(precision=10, scale=2), nullable=True),
        
        # Pattern Metadata
        sa.Column('occurrence_count', sa.Integer(), nullable=False, default=0),
        sa.Column('confidence_score', sa.Numeric(precision=5, scale=2), nullable=True),
        
        # Pattern State
        sa.Column('status', sa.String(), nullable=False, default='active'),
        sa.Column('is_confirmed', sa.Boolean(), default=False),
        
        # Detection Details
        sa.Column('detected_by_agent', sa.String(), nullable=True),
        sa.Column('detection_method', sa.String(), nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('first_transaction_date', sa.DateTime(timezone=True), nullable=True)
    )
    
    # Create pattern_transactions table
    op.create_table(
        'pattern_transactions',
        sa.Column('id', UUID(as_uuid=False), primary_key=True),
        sa.Column('pattern_id', UUID(as_uuid=False), sa.ForeignKey('spending_patterns.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('transaction_id', UUID(as_uuid=False), sa.ForeignKey('transactions.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('is_anomaly', sa.Boolean(), default=False),
        sa.Column('added_at', sa.DateTime(timezone=True), nullable=False)
    )
    
    # Create pattern_user_feedback table
    op.create_table(
        'pattern_user_feedback',
        sa.Column('id', UUID(as_uuid=False), primary_key=True),
        sa.Column('pattern_id', UUID(as_uuid=False), sa.ForeignKey('spending_patterns.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', UUID(as_uuid=False), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        
        # Feedback Type
        sa.Column('feedback_type', sa.String(), nullable=False),
        
        # User Adjustments
        sa.Column('adjusted_frequency_days', sa.Integer(), nullable=True),
        sa.Column('adjusted_amount', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('adjusted_variance_percentage', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('adjusted_next_date', sa.DateTime(timezone=True), nullable=True),
        
        # User Comments
        sa.Column('comment', sa.Text(), nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False)
    )
    
    # Create additional indexes for better query performance
    op.create_index('ix_spending_patterns_pattern_type', 'spending_patterns', ['pattern_type'])
    op.create_index('ix_spending_patterns_status', 'spending_patterns', ['status'])


def downgrade():
    # Drop tables in reverse order
    op.drop_table('pattern_user_feedback')
    op.drop_table('pattern_transactions')
    op.drop_table('spending_patterns')
