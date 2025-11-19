import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db import Base


class BudgetItem(Base):
    __tablename__ = "budget_items"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    budget_id = Column(UUID(as_uuid=False), ForeignKey('budgets.id', ondelete='CASCADE'), nullable=False, index=True)
    label = Column(String, nullable=False)
    category_id = Column(UUID(as_uuid=False), ForeignKey('categories.id', ondelete='SET NULL'), nullable=True)
    transaction_id = Column(UUID(as_uuid=False), ForeignKey('transactions.id', ondelete='SET NULL'), nullable=True)
    type = Column(String, nullable=False)
    amount = Column(Numeric(precision=10, scale=2), nullable=False)
    date = Column(DateTime(timezone=True), nullable=False)
    status = Column(String, nullable=True)
    
    # Relationships
    category = relationship("Category", backref="budget_items")
    transaction = relationship("Transaction", backref="budget_items")

