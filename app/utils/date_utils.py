"""
Date utilities for API operations.
"""
from datetime import datetime, timedelta
from calendar import monthrange


def get_month_start_date(date: datetime) -> datetime:
    """
    Get the first day of the month for the given date.
    
    Args:
        date: Any date in the target month
        
    Returns:
        datetime: First day of the month at 00:00:00
    """
    return datetime(date.year, date.month, 1)


def get_month_end_date(date: datetime) -> datetime:
    """
    Get the last day of the month for the given date, handling all month variations.
    
    Correctly detects:
    - February 28 (non-leap year)
    - February 29 (leap year)
    - 30-day months (April, June, September, November)
    - 31-day months (January, March, May, July, August, October, December)
    
    Args:
        date: Any date in the target month
        
    Returns:
        datetime: Last day of the month at 23:59:59
    """
    # monthrange returns (weekday_of_first_day, number_of_days_in_month)
    _, last_day_of_month = monthrange(date.year, date.month)
    
    return datetime(
        date.year,
        date.month,
        last_day_of_month,
        23,
        59,
        59
    )


def get_month_date_range(date: datetime) -> tuple[datetime, datetime]:
    """
    Get the start and end dates for the entire month.
    
    Args:
        date: Any date in the target month
        
    Returns:
        tuple: (first_day_of_month, last_day_of_month)
    """
    start = get_month_start_date(date)
    end = get_month_end_date(date)
    return start, end
