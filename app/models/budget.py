import uuid
from sqlalchemy import Column, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db import Base


class Budget(Base):
    __tablename__ = "budgets"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    date = Column(DateTime(timezone=True), nullable=False)
    
    # Relationship
    budget_items = relationship("BudgetItem", backref="budget", cascade="all, delete-orphan")

