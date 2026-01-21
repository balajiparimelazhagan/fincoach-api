"""
Pattern Transaction Model - links transactions to discovered patterns.
Explicit many-to-many relationship (one transactor can have multiple patterns).
Append-only table to avoid reassignment bugs.
"""
from sqlalchemy import Column, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.db import Base


class PatternTransaction(Base):
    """
    Links transactions to recurring patterns.
    
    Purpose:
    - Explicitly track which transactions belong to which pattern
    - Support multiple patterns per transactor (e.g., ₹100 and ₹1000 mutual fund SIPs)
    - Prevent reassignment bugs during pattern re-discovery
    
    Append-only: Once linked, never deleted (unless pattern is deleted)
    """
    __tablename__ = "pattern_transactions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Links
    recurring_pattern_id = Column(
        UUID(as_uuid=True),
        ForeignKey('recurring_patterns.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    transaction_id = Column(
        UUID(as_uuid=True),
        ForeignKey('transactions.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    
    # Metadata
    linked_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    
    # Relationships
    pattern = relationship("RecurringPattern", backref="pattern_transactions")
    transaction = relationship("Transaction", backref="pattern_transactions")
    
    # Constraints and indexes
    __table_args__ = (
        # Prevent duplicate links
        UniqueConstraint('recurring_pattern_id', 'transaction_id', name='uq_pattern_transaction'),
        # Query by pattern
        Index('ix_pattern_transactions_pattern_id', 'recurring_pattern_id'),
        # Query by transaction (to check if already assigned)
        Index('ix_pattern_transactions_transaction_id', 'transaction_id'),
    )
    
    def __repr__(self):
        return f"<PatternTransaction(pattern={self.recurring_pattern_id}, txn={self.transaction_id})>"
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": str(self.id),
            "recurring_pattern_id": str(self.recurring_pattern_id),
            "transaction_id": str(self.transaction_id),
            "linked_at": self.linked_at.isoformat() if self.linked_at else None,
        }
