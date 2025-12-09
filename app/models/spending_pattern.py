import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Numeric, Integer, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db import Base


class SpendingPattern(Base):
    """
    Tracks detected spending patterns for users.
    Supports both bill patterns (utilities, subscriptions) and recurring transactions (rent, family).
    """
    __tablename__ = "spending_patterns"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    user_id = Column(UUID(as_uuid=False), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    transactor_id = Column(UUID(as_uuid=False), ForeignKey('transactors.id', ondelete='SET NULL'), nullable=True)
    category_id = Column(UUID(as_uuid=False), ForeignKey('categories.id', ondelete='SET NULL'), nullable=True)
    
    # Pattern Classification
    pattern_type = Column(String, nullable=False)  # 'bill' or 'recurring_transaction'
    pattern_name = Column(String, nullable=True)  # e.g., "Monthly Airtel Bill", "Rent Payment"
    
    # Frequency Detection
    frequency_days = Column(Integer, nullable=True)  # Detected frequency in days (28, 30, 54, 56, 120, etc.)
    frequency_label = Column(String, nullable=True)  # Human-readable: "Monthly", "Every 28 days", "Quarterly"
    frequency_variance_days = Column(Integer, nullable=True)  # Allowed variance in days (±2, ±5, etc.)
    
    # Amount Analysis
    average_amount = Column(Numeric(precision=10, scale=2), nullable=True)
    min_amount = Column(Numeric(precision=10, scale=2), nullable=True)
    max_amount = Column(Numeric(precision=10, scale=2), nullable=True)
    amount_variance_percentage = Column(Numeric(precision=5, scale=2), nullable=True)  # e.g., 15.50 for ±15.5%
    
    # Prediction
    last_transaction_date = Column(DateTime(timezone=True), nullable=True)
    next_expected_date = Column(DateTime(timezone=True), nullable=True)  # Predicted next transaction date
    expected_amount = Column(Numeric(precision=10, scale=2), nullable=True)  # Predicted amount
    
    # Pattern Metadata
    occurrence_count = Column(Integer, nullable=False, default=0)  # Number of transactions in this pattern
    confidence_score = Column(Numeric(precision=5, scale=2), nullable=True)  # 0-100 confidence percentage
    
    # Pattern State
    status = Column(String, nullable=False, default='active')  # 'active', 'paused', 'ended'
    is_confirmed = Column(Boolean, default=False)  # User confirmed this pattern
    
    # Detection Details
    detected_by_agent = Column(String, nullable=True)  # 'bill_pattern_agent' or 'recurring_transaction_agent'
    detection_method = Column(String, nullable=True)  # Details about how pattern was detected
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    first_transaction_date = Column(DateTime(timezone=True), nullable=True)  # Date of first transaction in pattern
    
    # Relationships
    user = relationship("User", backref="spending_patterns")
    transactor = relationship("Transactor", backref="spending_patterns")
    category = relationship("Category", backref="spending_patterns")
    transactions = relationship("PatternTransaction", back_populates="pattern", cascade="all, delete-orphan")
    feedbacks = relationship("PatternUserFeedback", back_populates="pattern", cascade="all, delete-orphan")
