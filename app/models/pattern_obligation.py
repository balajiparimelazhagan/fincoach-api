"""
Pattern Obligation Model - tracks expected vs actual recurring payments.
Avoids recomputing "was it missed?" from transaction history.
Stateful obligation tracking for recurring patterns.
"""
from sqlalchemy import Column, String, DateTime, Numeric, ForeignKey, Index, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.db import Base


class ObligationStatus(str):
    """Obligation status constants"""
    EXPECTED = "EXPECTED"      # Future obligation
    FULFILLED = "FULFILLED"    # Matched by actual transaction
    MISSED = "MISSED"          # Past tolerance window, no match
    CANCELLED = "CANCELLED"    # Pattern paused/broken before fulfillment


class PatternObligation(Base):
    """
    Tracks expected recurring obligations and their fulfillment.
    
    Purpose:
    - Compute "next payment due" without re-analyzing history
    - Track whether obligations were met on time, late, or missed
    - Support confidence degradation based on actual behavior
    - Provide user-facing "upcoming payments" feature
    
    Lifecycle:
    1. Created when pattern is discovered or previous obligation is fulfilled
    2. Status = EXPECTED until actual transaction arrives
    3. Status = FULFILLED when matching transaction found (within tolerance)
    4. Status = MISSED if current_date > expected_date + tolerance
    5. Status = CANCELLED if pattern becomes BROKEN/PAUSED before fulfillment
    """
    __tablename__ = "pattern_obligations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Pattern link
    recurring_pattern_id = Column(
        UUID(as_uuid=True),
        ForeignKey('recurring_patterns.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    
    # Expected timing
    expected_date = Column(DateTime(timezone=True), nullable=False)
    tolerance_days = Column(Numeric(precision=5, scale=2), nullable=False)  # e.g., 3.00 for ±3 days
    
    # Expected amount (for budgeting, not matching)
    expected_min_amount = Column(Numeric(precision=10, scale=2), nullable=True)
    expected_max_amount = Column(Numeric(precision=10, scale=2), nullable=True)
    
    # Fulfillment tracking
    status = Column(String, nullable=False, default='EXPECTED')  # EXPECTED, FULFILLED, MISSED, CANCELLED
    fulfilled_by_transaction_id = Column(
        UUID(as_uuid=True),
        ForeignKey('transactions.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    fulfilled_at = Column(DateTime(timezone=True), nullable=True)  # Actual transaction date
    
    # Timing analysis (computed when fulfilled)
    days_early = Column(Numeric(precision=5, scale=2), nullable=True)  # Negative if late
    
    # Metadata
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    pattern = relationship("RecurringPattern", backref="obligations")
    fulfilled_by_transaction = relationship("Transaction", backref="fulfilled_obligations")
    
    # Constraints and indexes
    __table_args__ = (
        CheckConstraint("status IN ('EXPECTED', 'FULFILLED', 'MISSED', 'CANCELLED')", name='valid_obligation_status'),
        # Query upcoming obligations for a pattern
        Index('ix_pattern_obligations_pattern_expected', 'recurring_pattern_id', 'expected_date'),
        # Query upcoming obligations for a user (via pattern)
        Index('ix_pattern_obligations_status', 'status'),
        # Check if transaction already fulfilled an obligation
        Index('ix_pattern_obligations_fulfilled_by', 'fulfilled_by_transaction_id'),
    )
    
    def __repr__(self):
        return f"<PatternObligation(pattern={self.recurring_pattern_id}, expected={self.expected_date}, status={self.status})>"
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": str(self.id),
            "recurring_pattern_id": str(self.recurring_pattern_id),
            "expected_date": self.expected_date.isoformat() if self.expected_date else None,
            "tolerance_days": float(self.tolerance_days) if self.tolerance_days else None,
            "expected_min_amount": float(self.expected_min_amount) if self.expected_min_amount else None,
            "expected_max_amount": float(self.expected_max_amount) if self.expected_max_amount else None,
            "status": self.status,
            "fulfilled_by_transaction_id": str(self.fulfilled_by_transaction_id) if self.fulfilled_by_transaction_id else None,
            "fulfilled_at": self.fulfilled_at.isoformat() if self.fulfilled_at else None,
            "days_early": float(self.days_early) if self.days_early else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
