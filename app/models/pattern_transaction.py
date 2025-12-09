import uuid
from sqlalchemy import Column, ForeignKey, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db import Base


class PatternTransaction(Base):
    """
    Links transactions to spending patterns.
    Many-to-many relationship: a transaction can belong to multiple patterns,
    and a pattern consists of multiple transactions.
    """
    __tablename__ = "pattern_transactions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    pattern_id = Column(UUID(as_uuid=False), ForeignKey('spending_patterns.id', ondelete='CASCADE'), nullable=False, index=True)
    transaction_id = Column(UUID(as_uuid=False), ForeignKey('transactions.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Metadata
    is_anomaly = Column(Boolean, default=False)  # Transaction deviates significantly from pattern
    added_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    
    # Relationships
    pattern = relationship("SpendingPattern", back_populates="transactions")
    transaction = relationship("Transaction", backref="pattern_associations")
