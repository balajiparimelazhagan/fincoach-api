"""make sync job timestamps timezone aware

Revision ID: 037
Revises: 036
Create Date: 2026-04-30
"""
from alembic import op
import sqlalchemy as sa

revision = '037'
down_revision = '036'
branch_labels = None
depends_on = None


def upgrade():
    for table in ('email_transaction_sync_jobs', 'sms_transaction_sync_jobs'):
        for col in ('started_at', 'completed_at', 'created_at', 'updated_at'):
            op.alter_column(
                table, col,
                type_=sa.DateTime(timezone=True),
                existing_type=sa.DateTime(),
                existing_nullable=(col in ('started_at', 'completed_at')),
                postgresql_using=f'{col} AT TIME ZONE \'UTC\'',
            )


def downgrade():
    for table in ('email_transaction_sync_jobs', 'sms_transaction_sync_jobs'):
        for col in ('started_at', 'completed_at', 'created_at', 'updated_at'):
            op.alter_column(
                table, col,
                type_=sa.DateTime(),
                existing_type=sa.DateTime(timezone=True),
                existing_nullable=(col in ('started_at', 'completed_at')),
                postgresql_using=f'{col} AT TIME ZONE \'UTC\'',
            )
