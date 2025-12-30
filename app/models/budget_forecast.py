"""
Budget Forecast Model for storing historical user-visible forecast outputs.
Append-only: new forecast = new row. Not authoritative; can be safely regenerated.
"""
from sqlalchemy import Column, String, DateTime, Numeric, Text, Index, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.db import Base


class BudgetForecast(Base):
    """
    Model for storing historical budget forecast outputs.
    
    APPEND-ONLY: Never update, only insert new rows
    NOT AUTHORITATIVE: Safe to delete and regenerate
    USER-VISIBLE: Used to populate UI with spending forecasts
    
    Each row represents a forecast for a specific transactor + direction combo,
    generated at a specific point in time.
    
    Supports Case-6 (frequent variable): recurring_pattern_id can be NULL
    for non-recurring patterns tracked only in budget_forecasts.
    
    Example 1 (Recurring):
        Transactor: TNEB (electricity)
        Direction: DEBIT
        recurring_pattern_id: <uuid>
        Expected min/max: 900/1200
        Confidence: 0.95
        Explanation: "Detected monthly charge"
        
    Example 2 (Case-6: Frequent Variable):
        Transactor: Amazon
        Direction: DEBIT
        recurring_pattern_id: NULL (not in recurring_patterns table)
        Expected min/max: 1500/5000 (monthly aggregate)
        Confidence: 0.70
        Explanation: "Frequent spending with variable amounts"
    """
    __tablename__ = "budget_forecasts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Context
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    transactor_id = Column(UUID(as_uuid=True), ForeignKey('transactors.id', ondelete='CASCADE'), nullable=False)
    direction = Column(String, nullable=False)  # "DEBIT" or "CREDIT"
    
    # Link back to pattern (NULL for Case-6: frequent variable)
    recurring_pattern_id = Column(
        UUID(as_uuid=True),
        ForeignKey('recurring_patterns.id', ondelete='SET NULL'),
        nullable=True
    )
    
    # Forecast bounds (in user's currency)
    expected_min_amount = Column(Numeric(precision=10, scale=2), nullable=False)
    expected_max_amount = Column(Numeric(precision=10, scale=2), nullable=False)
    
    # User-facing confidence (may differ from pattern.confidence due to UI logic)
    confidence = Column(Numeric(precision=4, scale=3), nullable=False)  # 0.0 to 1.0
    
    # Explanation for UI
    explanation_text = Column(Text, nullable=True)  # e.g., "Detected monthly subscription" or "Frequent but variable"
    
    # Metadata
    generated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)  # When forecast was created
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)  # When row was inserted
    
    # Relationships
    user = relationship("User", backref="budget_forecasts")
    transactor = relationship("Transactor", backref="budget_forecasts")
    pattern = relationship("RecurringPattern", backref="budget_forecasts")
    
    # Indexes for efficient queries
    __table_args__ = (
        Index('ix_budget_forecasts_user_id', 'user_id'),
        Index('ix_budget_forecasts_user_generated_at', 'user_id', 'generated_at'),
        Index('ix_budget_forecasts_recurring_pattern_id', 'recurring_pattern_id'),
        Index('ix_budget_forecasts_transactor_id', 'transactor_id'),
    )
    
    def __repr__(self):
        return f"<BudgetForecast(transactor={self.transactor_id}, direction={self.direction}, min={self.expected_min_amount}, max={self.expected_max_amount})>"
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "transactor_id": str(self.transactor_id),
            "direction": self.direction,
            "recurring_pattern_id": str(self.recurring_pattern_id) if self.recurring_pattern_id else None,
            "expected_min_amount": float(self.expected_min_amount),
            "expected_max_amount": float(self.expected_max_amount),
            "confidence": float(self.confidence),
            "explanation_text": self.explanation_text,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
