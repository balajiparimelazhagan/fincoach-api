from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_db
from app.services.spending_analysis_service import SpendingAnalysisService
from app.models import SpendingAnalysisJob, RecurringPattern
from app.celery.celery_tasks import detect_or_update_recurring_pattern
from uuid import UUID

router = APIRouter()

@router.post("/api/v1/analytics/spending-patterns/analyze")
async def trigger_spending_analysis(user_id: UUID, db: AsyncSession = Depends(get_db)):
    service = SpendingAnalysisService(db)
    job = await service.create_job(user_id=user_id, triggered_by='MANUAL')
    detect_or_update_recurring_pattern.delay(str(user_id), str(job.id))
    return {"job_id": str(job.id), "status": job.status, "message": "Spending analysis job triggered successfully."}

@router.get("/api/v1/analytics/spending-patterns/jobs/{job_id}")
async def get_spending_analysis_job(job_id: UUID, db: AsyncSession = Depends(get_db)):
    service = SpendingAnalysisService(db)
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.get("/api/v1/analytics/spending-patterns")
async def list_spending_analysis_jobs(user_id: UUID, db: AsyncSession = Depends(get_db)):
    service = SpendingAnalysisService(db)
    jobs = await service.get_jobs(user_id)
    return jobs

@router.get("/api/v1/analytics/spending-patterns/{pattern_id}")
async def get_spending_pattern(pattern_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        RecurringPattern.__table__.select().where(RecurringPattern.id == pattern_id)
    )
    pattern = result.fetchone()
    if not pattern:
        raise HTTPException(status_code=404, detail="Pattern not found")
    return pattern
