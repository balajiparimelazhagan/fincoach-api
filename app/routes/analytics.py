from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db_session
from app.models.user import User
from app.dependencies import get_current_user, get_db
from app.services.spending_analysis_service import SpendingAnalysisService
from app.services.stats_service import calculate_period_stats, calculate_category_spending, get_comprehensive_stats
from app.models import SpendingAnalysisJob, RecurringPattern
from app.celery.celery_tasks import detect_or_update_recurring_pattern
from uuid import UUID

router = APIRouter(prefix="/analytics", tags=["Analytics"])

@router.post("/spending-patterns/analyze")
async def trigger_spending_analysis(user_id: UUID, db: AsyncSession = Depends(get_db)):
    service = SpendingAnalysisService(db)
    job = await service.create_job(user_id=user_id, triggered_by='MANUAL')
    detect_or_update_recurring_pattern.delay(str(user_id), str(job.id))
    return {"job_id": str(job.id), "status": job.status, "message": "Spending analysis job triggered successfully."}

@router.get("/spending-patterns/jobs/{job_id}")
async def get_spending_analysis_job(job_id: UUID, db: AsyncSession = Depends(get_db)):
    service = SpendingAnalysisService(db)
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.get("/spending-patterns")
async def list_spending_analysis_jobs(user_id: UUID, db: AsyncSession = Depends(get_db)):
    service = SpendingAnalysisService(db)
    jobs = await service.get_jobs(user_id)
    return jobs

@router.get("/spending-patterns/{pattern_id}")
async def get_spending_pattern(pattern_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        RecurringPattern.__table__.select().where(RecurringPattern.id == pattern_id)
    )
    pattern = result.fetchone()
    if not pattern:
        raise HTTPException(status_code=404, detail="Pattern not found")
    return pattern


@router.get("/stats/summary")
async def get_stats_summary(
    current_user: User = Depends(get_current_user),
    date_from: Optional[str] = Query(default=None, description="Start date (ISO8601)"),
    date_to: Optional[str] = Query(default=None, description="End date (ISO8601)"),
    session: AsyncSession = Depends(get_db_session),
):
    """Get summary statistics: total income, expense, and savings for a date range."""
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

