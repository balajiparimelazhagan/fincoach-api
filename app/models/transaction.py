import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    amount = Column(Numeric(precision=10, scale=2), nullable=False)
    transaction_id = Column(String, nullable=True)
    type = Column(String, nullable=False)
    date = Column(DateTime(timezone=True), nullable=False)
    transactor_id = Column(UUID(as_uuid=False), ForeignKey('transactors.id', ondelete='SET NULL'), nullable=True)
    category_id = Column(UUID(as_uuid=False), ForeignKey('categories.id', ondelete='SET NULL'), nullable=True)
    description = Column(String, nullable=True)
    confidence = Column(String, nullable=True)
    currency_id = Column(UUID(as_uuid=False), ForeignKey('currencies.id', ondelete='SET NULL'), nullable=True)
    user_id = Column(UUID(as_uuid=False), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    message_id = Column(String, nullable=True)
    
    # Relationships
    user = relationship("User", backref="transactions")
    category = relationship("Category", backref="transactions")
    currency = relationship("Currency", backref="transactions")
    transactor = relationship("Transactor", backref="transactions")

