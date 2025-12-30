"""
Spending Analysis Job Model for tracking pattern detection execution.
Operational metadata only - no pattern output or stats stored here.
"""
from sqlalchemy import Column, String, DateTime, Text, Index, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum

from app.db import Base


class SpendingAnalysisJobStatus(str, enum.Enum):
    """Status of spending analysis job - operational only"""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class SpendingAnalysisJobTrigger(str, enum.Enum):
    """How the job was triggered"""
    SCHEDULED = "SCHEDULED"  # Automatic scheduled run
    MANUAL = "MANUAL"  # User manually triggered


class SpendingAnalysisJob(Base):
    """
    Model for tracking spending analysis job execution.
    
    OPERATIONAL ONLY: Tracks async task state
    Does NOT store: pattern_type, confidence, forecast data, streak data, stats
    
    When job completes, its outputs go to:
    - recurring_patterns (new patterns detected)
    - recurring_pattern_streaks (streak state updates)
    - budget_forecasts (user-visible forecasts)
    
    This table only tracks: job lifecycle, errors, and celery task mapping.
    """
    __tablename__ = "spending_analysis_jobs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Optional: if analyzing a specific pattern
    transactor_id = Column(UUID(as_uuid=True), nullable=True)
    direction = Column(String, nullable=True)  # "DEBIT" or "CREDIT"
    
    # Execution state
    status = Column(String, nullable=False, default='PENDING', index=True)  # PENDING, PROCESSING, SUCCESS, FAILED
    triggered_by = Column(String, nullable=True)  # SCHEDULED, MANUAL
    
    # Job timing
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)  # Changed from completed_at
    
    # Error tracking
    error_message = Column(Text, nullable=True)  # Single error message
    error_log = Column(JSONB, default=list, nullable=False)  # Detailed error log
    
    # Celery task tracking
    celery_task_id = Column(String, nullable=True, unique=True, index=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Row-level locking for concurrency control
    is_locked = Column(Boolean, default=False, nullable=False, index=True)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    
    __table_args__ = (
        Index('ix_user_status_locked', 'user_id', 'status', 'is_locked'),
    )
    
    def __repr__(self):
        return f"<SpendingAnalysisJob(id={self.id}, user_id={self.user_id}, status={self.status})>"

