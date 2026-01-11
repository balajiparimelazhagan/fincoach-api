"""
Pydantic schemas for transaction-related API requests and responses.
"""
from datetime import datetime
from typing import Optional
from enum import Enum

from pydantic import BaseModel, Field, validator


class UpdateScope(str, Enum):
    """Enum for transaction update scopes."""
    SINGLE = "single"
    CURRENT_AND_FUTURE = "current_and_future"
    MONTH_ONLY = "month_only"
    MONTH_AND_FUTURE = "month_and_future"


class TransactionUpdateRequest(BaseModel):
    """Schema for updating a single transaction."""
    category_id: Optional[str] = Field(None, description="New category ID")
    transactor_label: Optional[str] = Field(None, description="New transactor label")

    class Config:
        json_schema_extra = {
            "example": {
                "category_id": "cat_123",
                "transactor_label": "Grocery Store"
            }
        }


class BulkTransactionUpdateRequest(BaseModel):
    """Schema for bulk updating transactions."""
    category_id: Optional[str] = Field(None, description="New category ID")
    transactor_label: Optional[str] = Field(None, description="New transactor label")
    update_scope: UpdateScope = Field(..., description="Scope of the update operation")

    @validator('update_scope')
    def validate_scope(cls, v):
        """Validate that update_scope is a valid enum value."""
        if isinstance(v, str):
            try:
                return UpdateScope(v)
            except ValueError:
                raise ValueError(
                    f"Invalid update_scope. Must be one of: {', '.join([s.value for s in UpdateScope])}"
                )
        return v

    class Config:
        use_enum_values = True
        json_schema_extra = {
            "example": {
                "category_id": "cat_123",
                "transactor_label": "Grocery Store",
                "update_scope": "month_and_future"
            }
        }


class TransactorResponse(BaseModel):
    """Schema for transactor in transaction response."""
    id: str
    name: str
    picture: Optional[str] = None
    label: Optional[str] = None

    class Config:
        from_attributes = True


class CategoryResponse(BaseModel):
    """Schema for category in transaction response."""
    id: str
    label: str
    picture: Optional[str] = None

    class Config:
        from_attributes = True


class AccountResponse(BaseModel):
    """Schema for account in transaction response."""
    id: str
    account_last_four: str
    bank_name: str
    type: str

    class Config:
        from_attributes = True


class TransactionResponse(BaseModel):
    """Schema for transaction response."""
    id: str
    amount: Optional[int] = None
    transaction_id: Optional[str] = None
    type: str
    date: Optional[datetime] = None
    transactor_id: Optional[str] = None
    transactor: Optional[TransactorResponse] = None
    category_id: Optional[str] = None
    category: Optional[CategoryResponse] = None
    description: Optional[str] = None
    confidence: Optional[str] = None
    currency_id: Optional[str] = None
    user_id: Optional[str] = None
    message_id: Optional[str] = None
    account_id: Optional[str] = None
    account: Optional[AccountResponse] = None

    class Config:
        from_attributes = True


class BulkUpdateResponse(BaseModel):
    """Schema for bulk update response."""
    updated_count: int = Field(..., description="Number of transactions updated")
    transaction: TransactionResponse = Field(..., description="The updated transaction")


class TransactionListResponse(BaseModel):
    """Schema for transaction list response."""
    count: int = Field(..., description="Total count of transactions matching filters")
    items: list[TransactionResponse] = Field(..., description="List of transactions")
