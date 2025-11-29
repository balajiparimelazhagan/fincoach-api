"""create spend_analysis table

Revision ID: 013
Revises: 012
Create Date: 2025-11-28 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '013'
down_revision: Union[str, None] = '012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create table
    op.create_table(
        'spend_analysis',
        sa.Column(
            'id',
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text('gen_random_uuid()')
        ),

        # User reference
        sa.Column('user_id', postgresql.UUID(as_uuid=False), nullable=False),

        # Pattern information
        sa.Column('pattern_name', sa.String(), nullable=False),
        sa.Column('category_id', postgresql.UUID(as_uuid=False), nullable=True),  # no FK

        # Recurrence detection
        sa.Column('recurrence_type', sa.String(), nullable=False),  # monthly | weekly | yearly
        sa.Column('recurrence_interval', sa.Integer(), nullable=True),

        # Vendor source
        sa.Column('source_vendor', sa.String(), nullable=True),

        # Prediction fields
        sa.Column('next_prediction_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('predicted_amount', sa.Numeric(10, 2), nullable=True),

        # Agent reasoning
        sa.Column('confidence_score', sa.Numeric(5, 2), nullable=True),
        sa.Column('agent_notes', sa.Text(), nullable=True),

        # Notifications
        sa.Column('notification_sent', sa.Boolean(), server_default=sa.text('FALSE'), nullable=False),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # Foreign key only for user_id
    op.create_foreign_key(
        'fk_spend_analysis_user_id',
        'spend_analysis',
        'users',
        ['user_id'],
        ['id'],
        ondelete='CASCADE'
    )

    # Indexes
    op.create_index('ix_spend_analysis_id', 'spend_analysis', ['id'], unique=False)
    op.create_index('ix_spend_analysis_user_id', 'spend_analysis', ['user_id'], unique=False)
    op.create_index('ix_spend_analysis_next_prediction_date', 'spend_analysis', ['next_prediction_date'], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_spend_analysis_next_prediction_date', table_name='spend_analysis')
    op.drop_index('ix_spend_analysis_user_id', table_name='spend_analysis')
    op.drop_index('ix_spend_analysis_id', table_name='spend_analysis')

    # Drop foreign key
    op.drop_constraint('fk_spend_analysis_user_id', 'spend_analysis', type_='foreignkey')

    # Drop table
    op.drop_table('spend_analysis')
