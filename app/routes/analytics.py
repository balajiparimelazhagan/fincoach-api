from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db_session
from app.models.user import User
from app.dependencies import get_current_user

router = APIRouter(prefix="/analytics", tags=["Analytics"])

# ============================================================================
# STATISTICS ENDPOINTS
# ============================================================================

@router.get("/stats/summary")
async def get_stats_summary(
    current_user: User = Depends(get_current_user),
    date_from: Optional[str] = Query(default=None, description="Start date (ISO8601)"),
    date_to: Optional[str] = Query(default=None, description="End date (ISO8601)"),
    session: AsyncSession = Depends(get_db_session),
):
    """Get summary statistics: total income, expense, and savings for a date range."""
    from app.services.stats_service import calculate_period_stats
    
    try:
        if date_from:
            date_from_obj = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
            if date_from_obj.tzinfo is None:
                date_from_obj = date_from_obj.replace(tzinfo=timezone.utc)
        else:
            date_from_obj = None
            
        if date_to:
            date_to_obj = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
            if date_to_obj.tzinfo is None:
                date_to_obj = date_to_obj.replace(tzinfo=timezone.utc)
        else:
            date_to_obj = None
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use ISO8601 format.")
    
    stats = await calculate_period_stats(
        session,
        str(current_user.id),
        date_from=date_from_obj,
        date_to=date_to_obj,
    )
    return stats


@router.get("/stats/spending-by-category")
async def get_spending_by_category(
    current_user: User = Depends(get_current_user),
    date_from: Optional[str] = Query(default=None, description="Start date (ISO8601)"),
    date_to: Optional[str] = Query(default=None, description="End date (ISO8601)"),
    session: AsyncSession = Depends(get_db_session),
):
    """Get spending breakdown by category for a date range."""
    from app.services.stats_service import calculate_category_spending
    
    try:
        if date_from:
            date_from_obj = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
            if date_from_obj.tzinfo is None:
                date_from_obj = date_from_obj.replace(tzinfo=timezone.utc)
        else:
            date_from_obj = None
            
        if date_to:
            date_to_obj = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
            if date_to_obj.tzinfo is None:
                date_to_obj = date_to_obj.replace(tzinfo=timezone.utc)
        else:
            date_to_obj = None
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use ISO8601 format.")
    
    categories = await calculate_category_spending(
        session,
        str(current_user.id),
        date_from=date_from_obj,
        date_to=date_to_obj,
    )
    return {"categories": categories}


@router.get("/stats/comprehensive")
async def get_comprehensive_stats_endpoint(
    current_user: User = Depends(get_current_user),
    date_from: Optional[str] = Query(default=None, description="Start date (ISO8601)"),
    date_to: Optional[str] = Query(default=None, description="End date (ISO8601)"),
    session: AsyncSession = Depends(get_db_session),
):
    """Get comprehensive statistics including income, expense, savings, and category breakdown."""
    from app.services.stats_service import get_comprehensive_stats
    
    try:
        if date_from:
            date_from_obj = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
            if date_from_obj.tzinfo is None:
                date_from_obj = date_from_obj.replace(tzinfo=timezone.utc)
        else:
            date_from_obj = None
            
        if date_to:
            date_to_obj = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
            if date_to_obj.tzinfo is None:
                date_to_obj = date_to_obj.replace(tzinfo=timezone.utc)
        else:
            date_to_obj = None
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use ISO8601 format.")
    
    stats = await get_comprehensive_stats(
        session,
        str(current_user.id),
        date_from=date_from_obj,
        date_to=date_to_obj,
    )
    return stats
