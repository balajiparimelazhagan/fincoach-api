from typing import Optional
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel


class TransactionBase(BaseModel):
    amount: Decimal
    transaction_id: Optional[str] = None
    type: str
    date: datetime
    transactor_id: Optional[str] = None
    category_id: Optional[str] = None
    description: Optional[str] = None
    confidence: Optional[str] = None
    currency_id: Optional[str] = None
    message_id: Optional[str] = None


class TransactionCreate(TransactionBase):
    pass


class TransactionUpdate(BaseModel):
    amount: Optional[Decimal] = None
    transaction_id: Optional[str] = None
    type: Optional[str] = None
    date: Optional[datetime] = None
    transactor_id: Optional[str] = None
    category_id: Optional[str] = None
    description: Optional[str] = None
    confidence: Optional[str] = None
    currency_id: Optional[str] = None
    message_id: Optional[str] = None


class TransactionResponse(TransactionBase):
    id: str
    user_id: str

    class Config:
        from_attributes = True

