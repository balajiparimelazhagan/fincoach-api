"""
Email Sync Job Model for tracking email fetch and parse progress.
"""
from sqlalchemy import Column, String, Integer, Float, DateTime, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime
import uuid
import enum

from app.db import Base


class JobStatus(str, enum.Enum):
    """Status of email sync job"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class EmailSyncJob(Base):
    """Model for tracking email sync jobs"""
    __tablename__ = "email_sync_jobs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    status = Column(SQLEnum(JobStatus), default=JobStatus.PENDING, nullable=False, index=True)
    total_emails = Column(Integer, default=0, nullable=False)
    processed_emails = Column(Integer, default=0, nullable=False)
    parsed_transactions = Column(Integer, default=0, nullable=False)
    failed_emails = Column(Integer, default=0, nullable=False)
    progress_percentage = Column(Float, default=0.0, nullable=False)
    error_log = Column(JSONB, default=list, nullable=False)  # Store parsing failures
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<EmailSyncJob(id={self.id}, user_id={self.user_id}, status={self.status}, progress={self.progress_percentage}%)>"
