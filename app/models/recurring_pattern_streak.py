"""
Recurring Pattern Streak Model for tracking fast-changing pattern state.
Tracks whether recurring behavior is still holding via streaks and confidence multiplier.
"""
from sqlalchemy import Column, DateTime, Numeric, Integer, ForeignKey, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.db import Base


class RecurringPatternStreak(Base):
    """
    Model for tracking pattern streak state.
    
    FAST-CHANGING: Updated on every transaction sync
    AUTHORITATIVE: Never recomputed from history (state machine)
    
    Tracks:
    - Current streak count (consecutive occurrences matching pattern)
    - Longest streak count (historical max)
    - When pattern was last seen vs expected
    - Missed count (how many expected occurrences were missed)
    - Confidence multiplier (0.0-1.0 based on streak health)
    
    Example:
        Pattern: Monthly rent payment
        Current streak: 5 months (last payment on Dec 20)
        Expected: Dec 25 (5 days late)
        Missed: 0
        Confidence multiplier: 0.9 (slightly degraded due to timing shift)
    """
    __tablename__ = "recurring_pattern_streaks"
    
    recurring_pattern_id = Column(
        UUID(as_uuid=True),
        ForeignKey('recurring_patterns.id', ondelete='CASCADE'),
        primary_key=True
    )
    
    # Streak counts
    current_streak_count = Column(Integer, nullable=False, default=0)
    longest_streak_count = Column(Integer, nullable=False, default=0)
    
    # Timing tracking
    last_actual_date = Column(DateTime(timezone=True), nullable=True)  # When we last saw it
    last_expected_date = Column(DateTime(timezone=True), nullable=True)  # When we expected it
    
    # Miss tracking
    missed_count = Column(Integer, nullable=False, default=0)  # How many expected occurrences missed
    
    # Confidence multiplier (0.0 to 1.0)
    # Applied to pattern.confidence to get final user-facing confidence
    # 1.0 = all green (streak active, on time)
    # 0.5 = degraded (missed some, or late)
    # 0.0 = broken (too many misses)
    confidence_multiplier = Column(
        Numeric(precision=4, scale=3),
        nullable=False,
        default=1.0
    )
    
    # When was this last updated?
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    pattern = relationship("RecurringPattern", back_populates="streak", uselist=False)
    
    # Constraints
    __table_args__ = (
        CheckConstraint('confidence_multiplier >= 0.0 AND confidence_multiplier <= 1.0', name='streak_multiplier_range'),
    )
    
    def __repr__(self):
        return f"<RecurringPatternStreak(pattern={self.recurring_pattern_id}, current={self.current_streak_count}, multiplier={self.confidence_multiplier})>"
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "recurring_pattern_id": str(self.recurring_pattern_id),
            "current_streak_count": self.current_streak_count,
            "longest_streak_count": self.longest_streak_count,
            "last_actual_date": self.last_actual_date.isoformat() if self.last_actual_date else None,
            "last_expected_date": self.last_expected_date.isoformat() if self.last_expected_date else None,
            "missed_count": self.missed_count,
            "confidence_multiplier": float(self.confidence_multiplier),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
