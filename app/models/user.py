import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=True)
    google_id = Column(String, unique=True, index=True, nullable=False)
    picture = Column(String, nullable=True)
    access_token = Column(String, nullable=True)  
    refresh_token = Column(String, nullable=True)
    token_expiry = Column(DateTime(timezone=True), nullable=True)
    currency_id = Column(UUID(as_uuid=False), ForeignKey('currencies.id', ondelete='SET NULL'), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationship
    currency = relationship("Currency", backref="users")

