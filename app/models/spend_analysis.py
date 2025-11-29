from sqlalchemy import Column, String, DateTime, Numeric, Boolean, Integer, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.db import Base


class SpendAnalysis(Base):
    __tablename__ = 'spend_analysis'

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    user_id = Column(UUID(as_uuid=False), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    pattern_name = Column(String, nullable=False)
    transaction_type = Column(String, nullable=False, index=True)  # 'expense' | 'income'
    category_id = Column(UUID(as_uuid=False), nullable=True)
    recurrence_type = Column(String, nullable=False)
    recurrence_interval = Column(Integer, nullable=True)
    source_vendor = Column(String, nullable=True)
    next_prediction_date = Column(DateTime(timezone=True), nullable=False, index=True)
    predicted_amount = Column(Numeric(10, 2), nullable=True)
    confidence_score = Column(Numeric(5, 2), nullable=True)
    agent_notes = Column(Text, nullable=True)
    notification_sent = Column(Boolean, nullable=False, server_default='false')
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
