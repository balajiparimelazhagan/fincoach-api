from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.models.user import User
from app.dependencies import get_current_user
from app.services.account_stats_service import (
    get_user_accounts,
    get_account_by_id,
    get_user_accounts_with_stats,
)
from app.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/accounts", tags=["Accounts"])


def _serialize_account(account):
    """Serialize an Account object to a dictionary."""
    return {
        "id": account.id,
        "account_last_four": account.account_last_four,
        "bank_name": account.bank_name,
        "type": account.type.value,
        "user_id": account.user_id,
        "created_at": account.created_at.isoformat() if account.created_at else None,
        "updated_at": account.updated_at.isoformat() if account.updated_at else None,
    }


@router.get("/{account_id}")
async def get_account_by_id_route(
    account_id: str,
    session: AsyncSession = Depends(get_db_session),
):
    """Get a single account by ID."""
    account = await get_account_by_id(session, account_id)

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    return _serialize_account(account)


@router.get("")
async def list_accounts_route(
    current_user: User = Depends(get_current_user),
    account_type: Optional[str] = Query(default=None, description="Filter by account type"),
    bank_name: Optional[str] = Query(default=None, description="Filter by bank name"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
):
    """List all accounts for the authenticated user."""
    accounts, count = await get_user_accounts(
        session,
        current_user.id,
        account_type=account_type,
        bank_name=bank_name,
        limit=limit,
        offset=offset,
    )

    return {
        "count": count,
        "items": [_serialize_account(acc) for acc in accounts],
    }


@router.get("/stats/summary")
async def get_accounts_with_stats_route(
    current_user: User = Depends(get_current_user),
    date_from: Optional[datetime] = Query(default=None, description="Start date (ISO8601)"),
    date_to: Optional[datetime] = Query(default=None, description="End date (ISO8601)"),
    session: AsyncSession = Depends(get_db_session),
):
    """Get all accounts with income, expense, and savings statistics."""
    account_stats, count = await get_user_accounts_with_stats(
        session,
        current_user.id,
        date_from=date_from,
        date_to=date_to,
    )

    return {
        "count": count,
        "items": account_stats,
    }
