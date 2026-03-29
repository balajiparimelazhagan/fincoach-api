"""
Statistics Service
Handles calculation of income, expense, savings, and category-based spending.
"""
from calendar import monthrange
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from sqlalchemy import and_

from app.models.transaction import Transaction

IST = ZoneInfo("Asia/Kolkata")
from app.models.category import Category
from app.models.pattern_obligation import PatternObligation
from app.models.recurring_pattern import RecurringPattern
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


async def get_cashflow_daily_summary(
    session: AsyncSession,
    user_id: str,
    year: int,
    month: int,
) -> List[Dict[str, Any]]:
    """
    Return per-day cashflow summary for the given month.

    Args:
        session: SQLAlchemy async session
        user_id: UUID string of the user
        year: 4-digit year
        month: 1-indexed month (1=January … 12=December)

    Returns:
        List of {day, income, expense, predicted_bills} for every day in the month.
    """
    last_day = monthrange(year, month)[1]
    # Use IST-aware boundaries so UTC-stored TIMESTAMPTZ values are filtered correctly
    month_start = datetime(year, month, 1, tzinfo=IST)
    month_end = datetime(year, month, last_day, 23, 59, 59, tzinfo=IST)

    # Actual transactions
    tx_stmt = select(Transaction).filter(
        and_(
            Transaction.user_id == user_id,
            Transaction.date >= month_start,
            Transaction.date <= month_end,
        )
    )
    tx_result = await session.execute(tx_stmt)
    transactions = tx_result.scalars().all()

    # EXPECTED obligations (predicted bills) in this month
    obl_stmt = (
        select(PatternObligation)
        .join(RecurringPattern, PatternObligation.recurring_pattern_id == RecurringPattern.id)
        .filter(
            and_(
                RecurringPattern.user_id == user_id,
                PatternObligation.expected_date >= month_start,
                PatternObligation.expected_date <= month_end,
                PatternObligation.status == 'EXPECTED',
            )
        )
    )
    obl_result = await session.execute(obl_stmt)
    obligations = obl_result.scalars().all()

    # Build per-day buckets
    daily: Dict[int, Dict[str, float]] = {}

    def _bucket(day: int) -> Dict[str, float]:
        if day not in daily:
            daily[day] = {'income': 0.0, 'expense': 0.0, 'predicted_bills': 0.0}
        return daily[day]

    for tx in transactions:
        # Convert to IST so the day boundary matches what the user sees
        ist_day = tx.date.astimezone(IST).day if tx.date.tzinfo else tx.date.day
        b = _bucket(ist_day)
        if tx.type == 'income':
            b['income'] += float(tx.amount)
        elif tx.type == 'expense':
            b['expense'] += abs(float(tx.amount))

    for obl in obligations:
        b = _bucket(obl.expected_date.day)
        if obl.expected_min_amount and obl.expected_max_amount:
            amount = (float(obl.expected_min_amount) + float(obl.expected_max_amount)) / 2
        elif obl.expected_min_amount:
            amount = float(obl.expected_min_amount)
        elif obl.expected_max_amount:
            amount = float(obl.expected_max_amount)
        else:
            amount = 0.0
        b['predicted_bills'] += amount

    return [
        {
            'day': day,
            'income': round(daily.get(day, {}).get('income', 0)),
            'expense': round(daily.get(day, {}).get('expense', 0)),
            'predicted_bills': round(daily.get(day, {}).get('predicted_bills', 0)),
        }
        for day in range(1, last_day + 1)
    ]


async def get_category_budgets(
    session: AsyncSession,
    user_id: str,
    year: int,
    month: int,
) -> List[Dict[str, Any]]:
    """
    Return category spending for the given month vs 3-month historical average.

    For each category that has expense transactions in the selected month OR the
    prior 3 months, returns:
    - category_id, category_name
    - has_pattern: whether any transactor in this category has an active expense pattern
    - current_actual: total spent in the selected month
    - avg_last_3_months: average monthly spend over the 3 months before the selected month
    - over_budget: True if current_actual > avg_last_3_months
    - over_amount: amount by which the user is over their average (0 if under)
    """
    # Use IST-aware boundaries so UTC-stored TIMESTAMPTZ values are filtered correctly
    last_day = monthrange(year, month)[1]
    curr_start = datetime(year, month, 1, tzinfo=IST)
    curr_end = datetime(year, month, last_day, 23, 59, 59, tzinfo=IST)

    # Start of 3 months before the selected month
    hist_month = month - 3
    hist_year = year
    if hist_month <= 0:
        hist_month += 12
        hist_year -= 1
    hist_start = datetime(hist_year, hist_month, 1, tzinfo=IST)

    # Current month expense transactions
    curr_stmt = select(Transaction).filter(
        and_(
            Transaction.user_id == user_id,
            Transaction.type == 'expense',
            Transaction.date >= curr_start,
            Transaction.date <= curr_end,
        )
    ).options(joinedload(Transaction.category))
    curr_result = await session.execute(curr_stmt)
    curr_txs = curr_result.scalars().unique().all()

    # Last 3 months expense transactions
    hist_stmt = select(Transaction).filter(
        and_(
            Transaction.user_id == user_id,
            Transaction.type == 'expense',
            Transaction.date >= hist_start,
            Transaction.date < curr_start,
        )
    ).options(joinedload(Transaction.category))
    hist_result = await session.execute(hist_stmt)
    hist_txs = hist_result.scalars().unique().all()

    # Active expense pattern transactor IDs
    pat_stmt = select(RecurringPattern).filter(
        and_(
            RecurringPattern.user_id == user_id,
            RecurringPattern.status == 'ACTIVE',
            RecurringPattern.direction.in_(['expense', 'DEBIT']),
        )
    )
    pat_result = await session.execute(pat_stmt)
    patterns = pat_result.scalars().all()
    expense_pattern_transactor_ids = {str(p.transactor_id) for p in patterns}

    # Aggregate current month by category
    curr_by_cat: Dict[str, Dict] = {}
    for tx in curr_txs:
        cat_key = str(tx.category_id) if tx.category_id else '__uncategorized__'
        cat_name = tx.category.label if tx.category else 'Uncategorized'
        if cat_key not in curr_by_cat:
            curr_by_cat[cat_key] = {'name': cat_name, 'total': 0.0, 'has_pattern': False}
        curr_by_cat[cat_key]['total'] += abs(float(tx.amount))
        if tx.transactor_id and str(tx.transactor_id) in expense_pattern_transactor_ids:
            curr_by_cat[cat_key]['has_pattern'] = True

    # Aggregate historical by category (also collect names + has_pattern for history-only rows)
    hist_by_cat: Dict[str, float] = {}
    hist_cat_names: Dict[str, str] = {}
    hist_has_pattern: Dict[str, bool] = {}
    for tx in hist_txs:
        cat_key = str(tx.category_id) if tx.category_id else '__uncategorized__'
        hist_by_cat[cat_key] = hist_by_cat.get(cat_key, 0.0) + abs(float(tx.amount))
        if cat_key not in hist_cat_names:
            hist_cat_names[cat_key] = tx.category.label if tx.category else 'Uncategorized'
        if tx.transactor_id and str(tx.transactor_id) in expense_pattern_transactor_ids:
            hist_has_pattern[cat_key] = True

    # Union of current-month and historical categories so we never miss a category
    all_cat_keys = set(curr_by_cat.keys()) | set(hist_by_cat.keys())

    result = []
    for cat_key in all_cat_keys:
        curr_data = curr_by_cat.get(cat_key, {
            'name': hist_cat_names.get(cat_key, 'Uncategorized'),
            'total': 0.0,
            'has_pattern': hist_has_pattern.get(cat_key, False),
        })
        hist_total = hist_by_cat.get(cat_key, 0.0)
        avg_3m = round(hist_total / 3) if hist_total > 0 else 0
        current = round(curr_data['total'])
        over_amount = max(0, current - avg_3m) if avg_3m > 0 else 0

        result.append({
            'category_id': None if cat_key == '__uncategorized__' else cat_key,
            'category_name': curr_data['name'],
            'has_pattern': curr_data['has_pattern'],
            'current_actual': current,
            'avg_last_3_months': avg_3m,
            'over_budget': over_amount > 0,
            'over_amount': over_amount,
        })

    return sorted(result, key=lambda x: x['current_actual'], reverse=True)


async def get_projected_summary(
    session: AsyncSession,
    user_id: str,
    year: int,
    month: int,
) -> Dict[str, Any]:
    """
    Sum of EXPECTED obligations for the remaining days in the given month.

    Only obligations with status='EXPECTED' and expected_date >= today are included,
    so fulfilled/missed obligations are excluded from the projection.

    Returns:
        { projected_income: int, projected_expense: int }
    """
    last_day = monthrange(year, month)[1]
    today = datetime.now(tz=IST)
    month_end = datetime(year, month, last_day, 23, 59, 59, tzinfo=IST)

    obl_stmt = (
        select(PatternObligation, RecurringPattern.direction)
        .join(RecurringPattern, PatternObligation.recurring_pattern_id == RecurringPattern.id)
        .filter(
            and_(
                RecurringPattern.user_id == user_id,
                PatternObligation.expected_date >= today,
                PatternObligation.expected_date <= month_end,
                PatternObligation.status == 'EXPECTED',
            )
        )
    )
    obl_result = await session.execute(obl_stmt)
    rows = obl_result.all()

    projected_income = 0.0
    projected_expense = 0.0

    for obl, direction in rows:
        if obl.expected_min_amount and obl.expected_max_amount:
            amount = (float(obl.expected_min_amount) + float(obl.expected_max_amount)) / 2
        elif obl.expected_min_amount:
            amount = float(obl.expected_min_amount)
        elif obl.expected_max_amount:
            amount = float(obl.expected_max_amount)
        else:
            amount = 0.0

        if direction in ('income', 'CREDIT'):
            projected_income += amount
        elif direction in ('expense', 'DEBIT'):
            projected_expense += amount

    return {
        "projected_income": round(projected_income),
        "projected_expense": round(projected_expense),
    }
