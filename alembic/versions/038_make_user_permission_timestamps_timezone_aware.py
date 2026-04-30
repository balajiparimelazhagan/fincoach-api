"""make user_permission timestamps timezone aware

Revision ID: 038
Revises: 037
Create Date: 2026-04-30
"""
from alembic import op
import sqlalchemy as sa

revision = '038'
down_revision = '037'
branch_labels = None
depends_on = None

_TABLE = 'user_permissions'
_COLS = ('granted_at', 'revoked_at', 'created_at', 'updated_at')
_NULLABLE = {'revoked_at'}


def upgrade():
    for col in _COLS:
        op.alter_column(
            _TABLE, col,
            type_=sa.DateTime(timezone=True),
            existing_type=sa.DateTime(),
            existing_nullable=(col in _NULLABLE),
            postgresql_using=f"{col} AT TIME ZONE 'UTC'",
        )


def downgrade():
    for col in _COLS:
        op.alter_column(
            _TABLE, col,
            type_=sa.DateTime(),
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=(col in _NULLABLE),
            postgresql_using=f"{col} AT TIME ZONE 'UTC'",
        )
