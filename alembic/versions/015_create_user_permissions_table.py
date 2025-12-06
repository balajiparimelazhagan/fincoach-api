"""create user_permissions table

Revision ID: 015
Revises: 014
Create Date: 2025-12-06

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '015'
down_revision = '014'
branch_labels = None
depends_on = None


def upgrade():
    # Create permission type enum (check if exists first)
    permission_type_enum = postgresql.ENUM(
        'sms_read', 
        'email_read', 
        'notification',
        name='permissiontype',
        create_type=False
    )
    permission_type_enum.create(op.get_bind(), checkfirst=True)
    
    # Create user_permissions table
    op.create_table(
        'user_permissions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('permission_type', postgresql.ENUM('sms_read', 'email_read', 'notification', name='permissiontype', create_type=False), nullable=False),
        sa.Column('granted_at', sa.DateTime(), nullable=False),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.String(), nullable=False, server_default='True'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )
    
    # Create indexes
    op.create_index('ix_user_permissions_user_id', 'user_permissions', ['user_id'])
    op.create_index('ix_user_permissions_permission_type', 'user_permissions', ['permission_type'])


def downgrade():
    # Drop indexes
    op.drop_index('ix_user_permissions_permission_type', 'user_permissions')
    op.drop_index('ix_user_permissions_user_id', 'user_permissions')
    
    # Drop table
    op.drop_table('user_permissions')
    
    # Drop enum (check if exists first)
    permission_type_enum = postgresql.ENUM(
        'sms_read', 
        'email_read', 
        'notification',
        name='permissiontype'
    )
    permission_type_enum.drop(op.get_bind(), checkfirst=True)
