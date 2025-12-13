import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, func, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db import Base
import enum


class AccountType(enum.Enum):
    """Enum for account types"""
    CREDIT = "credit"
    SAVINGS = "savings"
    CURRENT = "current"


class Account(Base):
    __tablename__ = "accounts"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    account_last_four = Column(String(4), nullable=False)
    bank_name = Column(String, nullable=False)
    type = Column(SQLEnum(AccountType, name='account_type_enum', values_callable=lambda obj: [e.value for e in obj]), nullable=False, default=AccountType.SAVINGS, server_default='savings')
    user_id = Column(UUID(as_uuid=False), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    user = relationship("User", backref="accounts")
