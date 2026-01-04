"""
Account Service
Handles account retrieval and statistics calculations.
"""
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_

from app.models.account import Account
from app.models.transaction import Transaction
from app.logging_config import get_logger
from app.utils.date_utils import get_month_date_range

logger = get_logger(__name__)


async def get_user_accounts(
    session: AsyncSession,
    user_id: str,
    account_type: Optional[str] = None,
    bank_name: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[List[Account], int]:
    """
    Get all accounts for a user with optional filtering.
    
    Args:
        session: SQLAlchemy async session
        user_id: UUID string of the user
        account_type: Optional account type filter (credit, savings, current)
        bank_name: Optional bank name filter (substring match)
        limit: Maximum items to return
        offset: Items to skip
        
    Returns:
        Tuple of (accounts list, total count)
    """
    conditions = [Account.user_id == user_id]
    
    if account_type:
        conditions.append(Account.type == account_type)
    
    if bank_name:
        conditions.append(Account.bank_name.ilike(f"%{bank_name}%"))

    stmt = select(Account)
    if conditions:
        stmt = stmt.filter(and_(*conditions))

    stmt = stmt.order_by(Account.created_at.desc()).offset(offset).limit(limit)

    result = await session.execute(stmt)
    accounts = result.scalars().all()
    
    return accounts, len(accounts)


async def get_account_by_id(
    session: AsyncSession,
    account_id: str,
) -> Optional[Account]:
    """
    Get a single account by ID.
    
    Args:
        session: SQLAlchemy async session
        account_id: Account UUID
        
    Returns:
        Account object or None if not found
    """
    result = await session.execute(
        select(Account).filter(Account.id == account_id)
    )
    return result.scalar_one_or_none()


async def calculate_account_statistics(
    session: AsyncSession,
    user_id: str,
    account: Account,
    date_from: datetime,
    date_to: datetime,
) -> Dict[str, Any]:
    """
    Calculate income, expense, and savings for an account.
    
    Args:
        session: SQLAlchemy async session
        user_id: UUID string of the user
        account: Account object
        date_from: Start date for calculations
        date_to: End date for calculations
        
    Returns:
        Dictionary with account data and statistics
    """
    # Get transactions for this specific account in the date range
    transactions_result = await session.execute(
        select(Transaction).filter(
            and_(
                Transaction.user_id == user_id,
                Transaction.account_id == account.id,
                Transaction.date >= date_from,
                Transaction.date <= date_to,
            )
        )
    )
    transactions = transactions_result.scalars().all()

    # Calculate income, expense, and savings as whole numbers
    income = sum(t.amount for t in transactions if t.type == 'income')
    expense = sum(abs(t.amount) for t in transactions if t.type == 'expense')
    savings = sum(abs(t.amount) for t in transactions if t.type == 'saving')

    return {
        "id": account.id,
        "account_last_four": account.account_last_four,
        "bank_name": account.bank_name,
        "type": account.type.value,
        "user_id": account.user_id,
        "created_at": account.created_at.isoformat() if account.created_at else None,
        "updated_at": account.updated_at.isoformat() if account.updated_at else None,
        "income": int(income) if income else 0,
        "expense": int(expense) if expense else 0,
        "savings": int(savings) if savings else 0,
    }


async def get_user_accounts_with_stats(
    session: AsyncSession,
    user_id: str,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> tuple[List[Dict[str, Any]], int]:
    """
    Get all accounts for a user with income, expense, and savings statistics.
    
    Args:
        session: SQLAlchemy async session
        user_id: UUID string of the user
        date_from: Optional start date (defaults to first day of current month)
        date_to: Optional end date (defaults to last day of current month)
        
    Returns:
        Tuple of (accounts with stats list, count)
    """
    # If date range not provided, use current month
    if not date_from or not date_to:
        now = datetime.utcnow()
        date_from, date_to = get_month_date_range(now)

    # Get all accounts for the user
    accounts_result = await session.execute(
        select(Account).filter(Account.user_id == user_id).order_by(Account.created_at.desc())
    )
    accounts = accounts_result.scalars().all()

    # Build response with statistics
    account_stats = []
    for account in accounts:
        stats = await calculate_account_statistics(
            session, user_id, account, date_from, date_to
        )
        account_stats.append(stats)

    return account_stats, len(account_stats)
