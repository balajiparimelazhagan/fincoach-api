"""
Email Transaction Sync Job Model for tracking email fetch and parse progress.
"""
from sqlalchemy import Column, String, Integer, Float, DateTime, Enum as SQLEnum, Date, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime
import uuid
import enum

from app.db import Base


class JobStatus(str, enum.Enum):
    """Status of email transactions sync job"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class EmailTransactionSyncJob(Base):
    """Model for tracking email transactions sync jobs"""
    __tablename__ = "email_transaction_sync_jobs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    status = Column(
        SQLEnum(JobStatus, name='jobstatus', values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        default=JobStatus.PENDING,
        nullable=False,
        index=True,
    )
    # Month batching fields for initial sync
    is_initial = Column(Boolean, default=False, nullable=False)  # True for initial 3-month batched sync
    month_start_date = Column(Date, nullable=True)  # Start of calendar month (e.g., 2025-12-01)
    month_end_date = Column(Date, nullable=True)  # End of calendar month (e.g., 2025-12-20 or 2025-12-31)
    month_sequence = Column(Integer, nullable=True)  # 1 for latest month, 2 for previous, 3 for oldest
    total_emails = Column(Integer, default=0, nullable=False)
    processed_emails = Column(Integer, default=0, nullable=False)
    parsed_transactions = Column(Integer, default=0, nullable=False)
    failed_emails = Column(Integer, default=0, nullable=False)
    skipped_emails = Column(Integer, default=0, nullable=False)  # Emails filtered by intent classifier
    progress_percentage = Column(Float, default=0.0, nullable=False)
    error_log = Column(JSONB, default=list, nullable=False)
    processed_message_ids = Column(JSONB, nullable=True)  # {"msg_id": true} for O(1) lookup, set to null after completion
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<EmailTransactionSyncJob(id={self.id}, user_id={self.user_id}, status={self.status}, progress={self.progress_percentage}%)>"
