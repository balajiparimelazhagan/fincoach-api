"""
Spending Analysis Job Model for tracking recurring pattern detection jobs.
Implements row-level locking to ensure only one job per user runs at a time.
"""
from sqlalchemy import Column, String, Integer, Float, DateTime, Enum as SQLEnum, Boolean, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime
import uuid
import enum

from app.db import Base


class SpendingAnalysisJobStatus(str, enum.Enum):
    """Status of spending analysis job"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class SpendingAnalysisJobTrigger(str, enum.Enum):
    """How the job was triggered"""
    SCHEDULED = "scheduled"  # Automatic scheduled run
    MANUAL = "manual"  # User manually triggered


class SpendingAnalysisJob(Base):
    """
    Model for tracking spending analysis jobs.
    
    Each job detects recurring transaction patterns for a user.
    Uses row-level locking to ensure only one job per user processes at a time.
    """
    __tablename__ = "spending_analysis_jobs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    status = Column(
        SQLEnum(SpendingAnalysisJobStatus, name='spending_analysis_job_status'),
        default=SpendingAnalysisJobStatus.PENDING,
        nullable=False,
        index=True,
    )
    triggered_by = Column(
        SQLEnum(SpendingAnalysisJobTrigger, name='spending_analysis_job_trigger'),
        default=SpendingAnalysisJobTrigger.MANUAL,
        nullable=False,
    )
    
    # Job execution timing
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Job results
    total_transactors_analyzed = Column(Integer, default=0, nullable=False)
    patterns_detected = Column(Integer, default=0, nullable=False)
    job_duration_seconds = Column(Float, nullable=True)
    
    # Error tracking
    error_log = Column(JSONB, default=list, nullable=False)  # List of error dicts
    
    # Celery task tracking
    celery_task_id = Column(String, nullable=True, unique=True, index=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Row-level locking for concurrency control
    # When a job is PROCESSING, this should be locked at DB level
    is_locked = Column(Boolean, default=False, nullable=False, index=True)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    
    __table_args__ = (
        Index('ix_user_status_locked', 'user_id', 'status', 'is_locked'),
    )
    
    def __repr__(self):
        return f"<SpendingAnalysisJob(id={self.id}, user_id={self.user_id}, status={self.status}, patterns={self.patterns_detected})>"
