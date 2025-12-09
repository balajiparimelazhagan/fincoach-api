import uuid
from sqlalchemy import Column, String, ForeignKey, DateTime, Numeric, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db import Base


class PatternUserFeedback(Base):
    """
    Stores user feedback on detected spending patterns.
    Users can accept, deny, or partially accept patterns with adjustments.
    """
    __tablename__ = "pattern_user_feedback"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    pattern_id = Column(UUID(as_uuid=False), ForeignKey('spending_patterns.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=False), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Feedback Type
    feedback_type = Column(String, nullable=False)  # 'accepted', 'denied', 'partially_accepted'
    
    # User Adjustments (for partial acceptance)
    adjusted_frequency_days = Column(Integer, nullable=True)  # User's correction to frequency
    adjusted_amount = Column(Numeric(precision=10, scale=2), nullable=True)  # User's correction to expected amount
    adjusted_variance_percentage = Column(Numeric(precision=5, scale=2), nullable=True)  # User's correction to variance
    adjusted_next_date = Column(DateTime(timezone=True), nullable=True)  # User's correction to next expected date
    
    # User Comments
    comment = Column(Text, nullable=True)  # Optional user explanation
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    pattern = relationship("SpendingPattern", back_populates="feedbacks")
    user = relationship("User", backref="pattern_feedbacks")
