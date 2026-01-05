"""
Statistics Service
Handles calculation of income, expense, savings, and category-based spending.
"""
from datetime import datetime
from typing import Dict, List, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from sqlalchemy import and_

from app.models.transaction import Transaction
from app.models.category import Category
from app.logging_config import get_logger
from app.utils.date_utils import get_month_date_range

logger = get_logger(__name__)


async def calculate_period_stats(
    session: AsyncSession,
    user_id: str,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Calculate total income, expense, and savings for a user in a date range.
    
    Args:
        session: SQLAlchemy async session
        user_id: UUID string of the user
        date_from: Optional start date (defaults to first day of current month)
        date_to: Optional end date (defaults to last day of current month)
        
    Returns:
        Dictionary with income, expense, and savings
    """
    # If date range not provided, use current month
    if not date_from or not date_to:
        now = datetime.utcnow()
        date_from, date_to = get_month_date_range(now)

    # Get transactions in the date range
    stmt = select(Transaction).filter(
        and_(
            Transaction.user_id == user_id,
            Transaction.date >= date_from,
            Transaction.date <= date_to,
        )
    ).options(
        joinedload(Transaction.category),
    )
    
    transactions_result = await session.execute(stmt)
    transactions = transactions_result.scalars().unique().all()

    # Calculate totals
    income = sum(t.amount for t in transactions if t.type == 'income')
    expense = sum(abs(t.amount) for t in transactions if t.type == 'expense')
    savings = sum(abs(t.amount) for t in transactions if t.type == 'saving')

    return {
        "income": int(income) if income else 0,
        "expense": int(expense) if expense else 0,
        "savings": int(savings) if savings else 0,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
    }


async def calculate_category_spending(
    session: AsyncSession,
    user_id: str,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """
    Calculate spending by category for a user in a date range.
    
    Args:
        session: SQLAlchemy async session
        user_id: UUID string of the user
        date_from: Optional start date (defaults to first day of current month)
        date_to: Optional end date (defaults to last day of current month)
        
    Returns:
        List of dictionaries with category name and total spending
    """
    # If date range not provided, use current month
    if not date_from or not date_to:
        now = datetime.utcnow()
        date_from, date_to = get_month_date_range(now)

    # Get all expense transactions in the date range
    stmt = select(Transaction).filter(
        and_(
            Transaction.user_id == user_id,
            Transaction.type == 'expense',
            Transaction.date >= date_from,
            Transaction.date <= date_to,
        )
    ).options(
        joinedload(Transaction.category),
    )
    
    transactions_result = await session.execute(stmt)
    transactions = transactions_result.scalars().unique().all()

    # Group spending by category
    category_spending: Dict[str, int] = {}
    for transaction in transactions:
        # Use category label if available, otherwise use 'Uncategorized'
        category_name = transaction.category.label if transaction.category else 'Uncategorized'
        if category_name not in category_spending:
            category_spending[category_name] = 0
        category_spending[category_name] += abs(transaction.amount)

    # Convert to list format
    result = [
        {
            "name": category,
            "amount": int(amount) if amount else 0,
        }
        for category, amount in sorted(
            category_spending.items(),
            key=lambda x: x[1],
            reverse=True
        )
    ]

    return result


async def get_comprehensive_stats(
    session: AsyncSession,
    user_id: str,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Get comprehensive statistics including income, expense, savings, and category breakdown.
    
    Args:
        session: SQLAlchemy async session
        user_id: UUID string of the user
        date_from: Optional start date (defaults to first day of current month)
        date_to: Optional end date (defaults to last day of current month)
        
    Returns:
        Dictionary with period stats and category spending breakdown
    """
    # If date range not provided, use current month
    if not date_from or not date_to:
        now = datetime.utcnow()
        date_from, date_to = get_month_date_range(now)

    period_stats = await calculate_period_stats(session, user_id, date_from, date_to)
    category_spending = await calculate_category_spending(session, user_id, date_from, date_to)

    return {
        **period_stats,
        "categories": category_spending,
    }
