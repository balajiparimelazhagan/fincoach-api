"""
User Permission Model for tracking user consents for SMS, Email, etc.
"""
from sqlalchemy import Column, String, DateTime, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone
import uuid
import enum

from app.db import Base


class PermissionType(str, enum.Enum):
    """Types of permissions that can be granted"""
    SMS_READ = "sms_read"
    EMAIL_READ = "email_read"
    NOTIFICATION = "notification"


class UserPermission(Base):
    """Model for tracking user permissions and consents"""
    __tablename__ = "user_permissions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    permission_type = Column(
        SQLEnum(PermissionType, name='permissiontype', values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
        index=True,
    )
    granted_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(String, nullable=False, default=True)  # Derived from revoked_at
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self):
        status = "active" if self.is_active else "revoked"
        return f"<UserPermission(user_id={self.user_id}, type={self.permission_type}, status={status})>"

    @property
    def is_granted(self) -> bool:
        """Check if permission is currently granted (not revoked)"""
        return self.revoked_at is None

    def revoke(self):
        """Revoke the permission"""
        self.revoked_at = datetime.now(timezone.utc)
        self.is_active = False
