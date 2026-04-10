"""
Budget API Routes

Endpoints for user-defined custom monthly budget items.
These items persist every month unless the user deletes them.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from pydantic import BaseModel, Field
import uuid

from app.db import get_db_session
from app.dependencies import get_current_user
from app.models.user import User
from app.models.custom_budget_item import CustomBudgetItem

router = APIRouter(prefix="/budget", tags=["budget"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class CustomItemResponse(BaseModel):
    id: str
    label: str
    amount: float
    day_of_month: Optional[int]
    section: str          # 'income' | 'bills' | 'savings' | 'flexible'
    category_id: Optional[str]
    category_name: Optional[str]
    transactor_id: Optional[str]
    transactor_name: Optional[str]
    account_id: Optional[str]
    account_label: Optional[str]
    paid_months: List[str] = []
    is_paid: Optional[bool] = None


class CreateCustomItemRequest(BaseModel):
    label: str = Field(..., min_length=1, max_length=200)
    amount: float = Field(..., gt=0)
    day_of_month: Optional[int] = Field(None, ge=1, le=28)
    section: str = Field(default='bills')
    category_id: Optional[str] = None
    transactor_id: Optional[str] = None
    account_id: Optional[str] = None


class MarkPaidRequest(BaseModel):
    year: int = Field(..., ge=2000, le=2100)
    month: int = Field(..., ge=1, le=12)
    transaction_id: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/custom-items", response_model=List[CustomItemResponse])
async def list_custom_items(
    year: Optional[int] = Query(None, description="If provided with month, returns is_paid for that month"),
    month: Optional[int] = Query(None, ge=1, le=12),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """List all active custom budget items for the authenticated user.
    Pass year+month to get is_paid status for that specific month.
    """
    result = await db.execute(
        select(CustomBudgetItem)
        .where(
            CustomBudgetItem.user_id == current_user.id,
            CustomBudgetItem.is_active == True,
        )
        .order_by(CustomBudgetItem.created_at)
    )
    items = result.scalars().all()
    month_key = f"{year}-{month:02d}" if year and month else None
    return [_to_response(item, month_key) for item in items]


@router.post("/custom-items", response_model=CustomItemResponse, status_code=status.HTTP_201_CREATED)
async def create_custom_item(
    request: CreateCustomItemRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Create a new custom budget item. It will appear in every month's budget."""
    if request.section not in ('income', 'bills', 'savings', 'flexible'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="section must be one of: income, bills, savings, flexible",
        )

    item = CustomBudgetItem(
        user_id=current_user.id,
        label=request.label,
        amount=request.amount,
        day_of_month=request.day_of_month,
        section=request.section,
        category_id=uuid.UUID(request.category_id) if request.category_id else None,
        transactor_id=uuid.UUID(request.transactor_id) if request.transactor_id else None,
        account_id=uuid.UUID(request.account_id) if request.account_id else None,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _to_response(item)


@router.patch("/custom-items/{item_id}/mark-paid", response_model=CustomItemResponse)
async def mark_custom_item_paid(
    item_id: str,
    request: MarkPaidRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Mark a custom budget item as paid for a given month."""
    item = await _get_item(db, item_id, current_user.id)

    month_key = f"{request.year}-{request.month:02d}"
    paid = list(item.paid_months or [])
    if month_key not in paid:
        paid.append(month_key)
        item.paid_months = paid
        await db.commit()
        await db.refresh(item)

    return _to_response(item, month_key)


@router.patch("/custom-items/{item_id}/unmark-paid", response_model=CustomItemResponse)
async def unmark_custom_item_paid(
    item_id: str,
    request: MarkPaidRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Unmark a custom budget item as paid for a given month."""
    item = await _get_item(db, item_id, current_user.id)

    month_key = f"{request.year}-{request.month:02d}"
    paid = [m for m in (item.paid_months or []) if m != month_key]
    item.paid_months = paid
    await db.commit()
    await db.refresh(item)

    return _to_response(item, month_key)


@router.delete("/custom-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_custom_item(
    item_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Soft-delete a custom budget item. It will no longer appear in any month."""
    item = await _get_item(db, item_id, current_user.id)
    item.is_active = False
    await db.commit()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_item(db: AsyncSession, item_id: str, user_id) -> CustomBudgetItem:
    result = await db.execute(
        select(CustomBudgetItem).where(
            CustomBudgetItem.id == uuid.UUID(item_id),
            CustomBudgetItem.user_id == user_id,
            CustomBudgetItem.is_active == True,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return item


def _to_response(item: CustomBudgetItem, month_key: str | None = None) -> CustomItemResponse:
    paid_months = item.paid_months or []
    return CustomItemResponse(
        id=str(item.id),
        label=item.label,
        amount=float(item.amount),
        day_of_month=item.day_of_month,
        section=item.section,
        category_id=str(item.category_id) if item.category_id else None,
        category_name=item.category.label if item.category else None,
        transactor_id=str(item.transactor_id) if item.transactor_id else None,
        transactor_name=(item.transactor.label or item.transactor.name) if item.transactor else None,
        account_id=str(item.account_id) if item.account_id else None,
        account_label=f"{item.account.bank_name} ····{item.account.account_last_four}" if item.account else None,
        paid_months=paid_months,
        is_paid=month_key in paid_months if month_key else None,
    )
