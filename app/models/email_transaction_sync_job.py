from sqlalchemy import Column, String, Integer, DateTime, Enum as SQLEnum, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime
import uuid
import enum

from app.db import Base


class JobStatus(str, enum.Enum):
    PENDING = "pending"      # kept for DB enum compatibility (no longer assigned on create)
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"        # kept for DB enum compatibility with sms_transaction_sync_jobs


class EmailTransactionSyncJob(Base):
    __tablename__ = "email_transaction_sync_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    status = Column(
        SQLEnum(JobStatus, name='jobstatus', values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        default=JobStatus.PROCESSING,
        nullable=False,
        index=True,
    )
    is_initial = Column(Boolean, default=False, nullable=False)
    total_emails = Column(Integer, default=0, nullable=False)
    processed_emails = Column(Integer, default=0, nullable=False)
    parsed_transactions = Column(Integer, default=0, nullable=False)
    failed_emails = Column(Integer, default=0, nullable=False)
    skipped_emails = Column(Integer, default=0, nullable=False)
    error_log = Column(JSONB, default=list, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<EmailTransactionSyncJob(id={self.id}, user_id={self.user_id}, status={self.status})>"
