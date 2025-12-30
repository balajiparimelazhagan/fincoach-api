"""
Recurring Pattern Model for storing detected recurring transaction patterns.
Stores stateful pattern metadata with confidence scores and streak tracking.
Immutable: detection output; Mutable: status, confidence (after streak calc), last_evaluated_at.
"""
from sqlalchemy import Column, String, DateTime, Numeric, Integer, Index, ForeignKey, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.db import Base


class RecurringPatternType(str):
    """Pattern type constants"""
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    BIWEEKLY = "BIWEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    ANNUAL = "ANNUAL"


class RecurringPatternStatus(str):
    """Pattern status constants"""
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    BROKEN = "BROKEN"


class AmountBehavior(str):
    """Amount behavior constants"""
    FIXED = "FIXED"
    VARIABLE = "VARIABLE"


class RecurringPattern(Base):
    """
    Model for detected recurring transaction patterns.
    
    STATEFUL: Represents "this recurring thing exists and is being tracked"
    
    Immutable:
    - id, user_id, transactor_id, direction, pattern_type, interval_days
    - amount_behavior, detected_at, detection_version
    
    Mutable (by streak task):
    - status, last_evaluated_at, confidence
    
    Does NOT store stats like avg_gap_days, avg_amount, etc.
    These are recomputed on demand from transactions table.
    """
    __tablename__ = "recurring_patterns"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    transactor_id = Column(UUID(as_uuid=True), ForeignKey('transactors.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Direction: DEBIT or CREDIT (differentiates spending from income)
    direction = Column(String, nullable=False)  # "DEBIT" or "CREDIT"
    
    # Pattern identification (immutable after detection)
    pattern_type = Column(String, nullable=False)  # "DAILY", "WEEKLY", "MONTHLY", etc.
    interval_days = Column(Integer, nullable=False)  # e.g., 7 for weekly, 30 for monthly
    amount_behavior = Column(String, nullable=False)  # "FIXED" or "VARIABLE"
    
    # Current state
    status = Column(String, nullable=False, default='ACTIVE')  # "ACTIVE", "PAUSED", "BROKEN"
    
    # Confidence after streak multiplier applied
    confidence = Column(Numeric(precision=4, scale=3), nullable=False)  # 0.0 to 1.0
    
    # Tracking metadata
    detected_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    last_evaluated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    detection_version = Column(Integer, nullable=False, default=1)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User", backref="recurring_patterns")
    transactor = relationship("Transactor", backref="recurring_patterns")
    streak = relationship("RecurringPatternStreak", uselist=False, back_populates="pattern", cascade="all, delete-orphan")
    
    # Indexes for common queries
    __table_args__ = (
        Index('uq_recurring_patterns_user_transactor_direction', 'user_id', 'transactor_id', 'direction', unique=True),
        Index('ix_recurring_patterns_user_status', 'user_id', 'status'),
        Index('ix_recurring_patterns_user_pattern_type', 'user_id', 'pattern_type'),
        Index('ix_recurring_patterns_user_transactor_direction', 'user_id', 'transactor_id', 'direction'),
    )
    
    def __repr__(self):
        return f"<RecurringPattern(transactor={self.transactor_id}, direction={self.direction}, type={self.pattern_type}, confidence={self.confidence}, status={self.status})>"
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "transactor_id": str(self.transactor_id),
            "direction": self.direction,
            "pattern_type": self.pattern_type,
            "interval_days": self.interval_days,
            "amount_behavior": self.amount_behavior,
            "status": self.status,
            "confidence": float(self.confidence),
            "detected_at": self.detected_at.isoformat() if self.detected_at else None,
            "last_evaluated_at": self.last_evaluated_at.isoformat() if self.last_evaluated_at else None,
            "detection_version": self.detection_version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
