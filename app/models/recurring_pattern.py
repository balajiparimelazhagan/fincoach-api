"""
Recurring Pattern Model for storing detected recurring transaction patterns.
Stores metadata about detected patterns with confidence scores.
Designed for future budget forecasting without pre-computed predictions.
"""
from sqlalchemy import Column, String, DateTime, Numeric, Integer, Float, Index, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.db import Base


class RecurringPatternType(str):
    """Pattern type constants"""
    FIXED_MONTHLY = "fixed_monthly"
    VARIABLE_MONTHLY = "variable_monthly"
    FLEXIBLE_MONTHLY = "flexible_monthly"
    BI_MONTHLY = "bi_monthly"
    QUARTERLY = "quarterly"
    CUSTOM_INTERVAL = "custom_interval"
    MULTI_MONTHLY = "multi_monthly"  # Multiple transactions per month


class RecurringPattern(Base):
    """
    Model for detected recurring transaction patterns.
    
    Stores pattern metadata without pre-computed forecasts.
    Forecasting can query this data later when needed.
    
    Example:
        Transactor: "TNEB Chennai" (electricity)
        Pattern Type: "variable_monthly"
        Frequency: "monthly"
        Confidence: 0.92
        Avg Amount: 950
        Min/Max: 800-1200
        Occurrences: 5
        Last Transaction: 2025-05-15
    """
    __tablename__ = "recurring_patterns"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    transactor_id = Column(UUID(as_uuid=True), ForeignKey('transactors.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Pattern identification
    pattern_type = Column(String, nullable=False)  # "fixed_monthly", "variable_monthly", etc.
    frequency = Column(String, nullable=False)  # "monthly", "bi-monthly", "quarterly", "28-day"
    
    # Confidence score (0-1) based on multiple factors
    # Calculated by analyzing: amount consistency, date consistency, frequency consistency
    confidence = Column(Float, nullable=False)  # 0.0 to 1.0
    
    # Amount analysis (in transaction currency)
    avg_amount = Column(Numeric(precision=12, scale=2), nullable=False)
    min_amount = Column(Numeric(precision=12, scale=2), nullable=False)
    max_amount = Column(Numeric(precision=12, scale=2), nullable=False)
    amount_variance_percent = Column(Float, nullable=False)  # Percentage variance from average
    
    # Occurrence tracking
    total_occurrences = Column(Integer, nullable=False)  # Total number of matching transactions
    occurrences_in_pattern = Column(Integer, nullable=False)  # Transactions matching the pattern
    
    # Date analysis
    avg_day_of_period = Column(Integer, nullable=True)  # Average day of month (1-31) or null for variable
    day_variance_days = Column(Integer, nullable=True)  # Std dev of days within period
    
    # Timeline tracking
    first_transaction_date = Column(DateTime(timezone=True), nullable=False)
    last_transaction_date = Column(DateTime(timezone=True), nullable=False)
    
    # Analysis metadata
    analyzed_at = Column(DateTime(timezone=True), nullable=False)  # When this pattern was detected
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User", backref="recurring_patterns")
    transactor = relationship("Transactor", backref="recurring_patterns")
    
    # Indexes for common queries
    __table_args__ = (
        Index('ix_user_transactor', 'user_id', 'transactor_id', unique=True),  # One pattern per transactor per user
        Index('ix_user_pattern_type', 'user_id', 'pattern_type'),
        Index('ix_user_confidence', 'user_id', 'confidence'),  # For sorting by confidence
    )
    
    def __repr__(self):
        return f"<RecurringPattern(transactor={self.transactor_id}, type={self.pattern_type}, confidence={self.confidence:.2f})>"
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "transactor_id": str(self.transactor_id),
            "pattern_type": self.pattern_type,
            "frequency": self.frequency,
            "confidence": self.confidence,
            "avg_amount": float(self.avg_amount),
            "min_amount": float(self.min_amount),
            "max_amount": float(self.max_amount),
            "amount_variance_percent": self.amount_variance_percent,
            "total_occurrences": self.total_occurrences,
            "occurrences_in_pattern": self.occurrences_in_pattern,
            "avg_day_of_period": self.avg_day_of_period,
            "day_variance_days": self.day_variance_days,
            "first_transaction_date": self.first_transaction_date.isoformat() if self.first_transaction_date else None,
            "last_transaction_date": self.last_transaction_date.isoformat() if self.last_transaction_date else None,
            "analyzed_at": self.analyzed_at.isoformat() if self.analyzed_at else None,
        }
