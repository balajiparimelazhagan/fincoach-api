"""
Pattern Analysis Job Model for tracking spending pattern analysis progress.
"""
from sqlalchemy import Column, String, Integer, Float, DateTime, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime, timezone
import uuid
import enum

from app.db import Base


class JobStatus(str, enum.Enum):
    """Status of pattern analysis job"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class PatternAnalysisJob(Base):
    """Model for tracking pattern analysis jobs"""
    __tablename__ = "pattern_analysis_jobs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    status = Column(
        SQLEnum(JobStatus, name='pattern_job_status', values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        default=JobStatus.PENDING,
        nullable=False,
        index=True,
    )
    
    # Analysis metrics
    total_transactors = Column(Integer, default=0, nullable=False)
    processed_transactors = Column(Integer, default=0, nullable=False)
    bill_patterns_found = Column(Integer, default=0, nullable=False)
    recurring_patterns_found = Column(Integer, default=0, nullable=False)
    total_patterns_found = Column(Integer, default=0, nullable=False)
    duplicates_removed = Column(Integer, default=0, nullable=False)
    
    # Progress tracking
    progress_percentage = Column(Float, default=0.0, nullable=False)
    current_step = Column(String, nullable=True)  # "analyzing_bills", "analyzing_recurring", "removing_duplicates", "completed"
    
    # Configuration
    force_reanalyze = Column(String, default=False, nullable=False)
    min_occurrences = Column(Integer, default=3, nullable=False)
    min_days_history = Column(Integer, default=60, nullable=False)
    
    # Error tracking
    error_log = Column(JSONB, default=list, nullable=False)
    error_message = Column(String, nullable=True)
    
    # Timestamps (stored as UTC without timezone in DB)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False)

    def __repr__(self):
        return f"<PatternAnalysisJob(id={self.id}, user_id={self.user_id}, status={self.status}, progress={self.progress_percentage}%)>"
