from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, or_

from app.db import get_db_session
from app.models.transaction import Transaction
from app.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/transactions", tags=["Transactions"])


def _serialize_transaction(t: Transaction):
    return {
        "id": t.id,
        "amount": float(t.amount) if t.amount is not None else None,
        "transaction_id": t.transaction_id,
        "type": t.type,
        "date": t.date.isoformat() if t.date else None,
        "transactor_id": t.transactor_id,
        "category_id": t.category_id,
        "description": t.description,
        "confidence": t.confidence,
        "currency_id": t.currency_id,
        "user_id": t.user_id,
        "message_id": t.message_id,
    }


@router.get("/{transaction_id}")
async def get_transaction_by_id(
    transaction_id: str,
    session: AsyncSession = Depends(get_db_session),
):
    """Return a single transaction by ID."""
    tx = (
        await session.execute(select(Transaction).filter(Transaction.id == transaction_id))
    ).scalar_one_or_none()

    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    return _serialize_transaction(tx)


@router.get("")
async def list_transactions(
    # Filters
    date_from: Optional[datetime] = Query(default=None, description="Start date (ISO8601)"),
    date_to: Optional[datetime] = Query(default=None, description="End date (ISO8601)"),
    description_contains: Optional[str] = Query(default=None, description="Substring match in description"),
    amount_min: Optional[float] = Query(default=None, description="Minimum amount"),
    amount_max: Optional[float] = Query(default=None, description="Maximum amount"),
    type: Optional[str] = Query(default=None, description="Transaction type"),
    user_id: Optional[str] = Query(default=None, description="Filter by user ID"),
    transactor_id: Optional[str] = Query(default=None, description="Filter by transactor ID"),
    category_id: Optional[str] = Query(default=None, description="Filter by category ID"),
    # Pagination
    limit: int = Query(default=50, ge=1, le=200, description="Max items to return"),
    offset: int = Query(default=0, ge=0, description="Items to skip"),
    session: AsyncSession = Depends(get_db_session),
):
    """
    List transactions with filtering. Read-only.

    Supported filters: date range, description substring, amount range,
    type, user_id, transactor_id, category_id.
    """
    conditions = []

    if date_from:
        conditions.append(Transaction.date >= date_from)
    if date_to:
        conditions.append(Transaction.date <= date_to)

    if description_contains:
        # Case-insensitive contains
        like_expr = f"%{description_contains}%"
        conditions.append(Transaction.description.ilike(like_expr))

    if amount_min is not None:
        conditions.append(Transaction.amount >= amount_min)
    if amount_max is not None:
        conditions.append(Transaction.amount <= amount_max)

    if type:
        conditions.append(Transaction.type == type)
    if user_id:
        conditions.append(Transaction.user_id == user_id)
    if transactor_id:
        conditions.append(Transaction.transactor_id == transactor_id)
    if category_id:
        conditions.append(Transaction.category_id == category_id)

    stmt = select(Transaction)
    if conditions:
        stmt = stmt.filter(and_(*conditions))

    stmt = stmt.order_by(Transaction.date.desc()).offset(offset).limit(limit)

    result = await session.execute(stmt)
    transactions = result.scalars().all()

    return {
        "count": len(transactions),
        "items": [_serialize_transaction(t) for t in transactions],
    }
