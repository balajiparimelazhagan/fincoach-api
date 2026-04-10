import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Numeric, Integer, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db import Base


class CustomBudgetItem(Base):
    __tablename__ = "custom_budget_items"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    user_id = Column(UUID(as_uuid=False), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    label = Column(String, nullable=False)
    amount = Column(Numeric(precision=10, scale=2), nullable=False)
    # 1–28 for a fixed day each month, NULL = flexible (no fixed date)
    day_of_month = Column(Integer, nullable=True)
    # One of: 'income' | 'bills' | 'savings' | 'flexible'
    section = Column(String, nullable=False, default='bills')
    category_id = Column(UUID(as_uuid=False), ForeignKey('categories.id', ondelete='SET NULL'), nullable=True)
    transactor_id = Column(UUID(as_uuid=False), ForeignKey('transactors.id', ondelete='SET NULL'), nullable=True)
    account_id = Column(UUID(as_uuid=False), ForeignKey('accounts.id', ondelete='SET NULL'), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    # List of "YYYY-MM" strings, e.g. ["2026-04", "2026-05"]
    paid_months = Column(JSONB, nullable=False, server_default='[]', default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships (read-only lookups for serialisation)
    category = relationship("Category", backref="custom_budget_items", lazy="selectin")
    transactor = relationship("Transactor", backref="custom_budget_items", lazy="selectin")
    account = relationship("Account", backref="custom_budget_items", lazy="selectin")

    def to_dict(self, month_key: str | None = None):
        d = {
            "id": str(self.id),
            "label": self.label,
            "amount": float(self.amount),
            "day_of_month": self.day_of_month,
            "section": self.section,
            "category_id": str(self.category_id) if self.category_id else None,
            "category_name": self.category.label if self.category else None,
            "transactor_id": str(self.transactor_id) if self.transactor_id else None,
            "transactor_name": (self.transactor.label or self.transactor.name) if self.transactor else None,
            "account_id": str(self.account_id) if self.account_id else None,
            "account_label": f"{self.account.bank_name} ····{self.account.account_last_four}" if self.account else None,
            "paid_months": self.paid_months or [],
        }
        if month_key is not None:
            d["is_paid"] = month_key in (self.paid_months or [])
        return d
