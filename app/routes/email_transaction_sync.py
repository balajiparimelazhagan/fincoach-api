from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.models.email_transaction_sync_job import EmailTransactionSyncJob, JobStatus
from app.models.user import User
from app.celery.celery_tasks import fetch_user_emails_initial
from app.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/email-transaction-sync", tags=["Email Transaction Sync"])


@router.post("/start/{user_id}")
async def start_email_transaction_sync(
    user_id: str,
    months: int = Query(default=3, ge=1, le=12),
    session: AsyncSession = Depends(get_db_session)
):
    user = (await session.execute(select(User).filter_by(id=user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    existing_job = (await session.execute(
        select(EmailTransactionSyncJob).filter_by(user_id=user_id, status=JobStatus.PROCESSING)
    )).scalar_one_or_none()
    if existing_job:
        return {
            "message": "Sync already in progress",
            "job_id": str(existing_job.id),
            "status": "processing"
        }

    task = fetch_user_emails_initial.delay(user_id, months)
    logger.info(f"Started email transaction sync for user {user_id} (task_id: {task.id})")

    return {
        "message": "Email transaction sync started",
        "task_id": task.id,
        "user_id": user_id,
        "months": months
    }


@router.get("/status/{user_id}")
async def get_email_transaction_sync_status(
    user_id: str,
    session: AsyncSession = Depends(get_db_session)
):
    job = (await session.execute(
        select(EmailTransactionSyncJob)
        .filter_by(user_id=user_id)
        .order_by(EmailTransactionSyncJob.created_at.desc())
    )).scalar_one_or_none()

    if not job:
        return {"status": "not_started", "message": "No email transaction sync jobs found"}

    progress = round((job.processed_emails / job.total_emails * 100) if job.total_emails > 0 else 0, 2)

    return {
        "job_id": str(job.id),
        "status": job.status.value,
        "sync_type": "initial" if job.is_initial else "incremental",
        "progress": progress,
        "total_emails": job.total_emails,
        "processed_emails": job.processed_emails,
        "parsed_transactions": job.parsed_transactions,
        "failed_emails": job.failed_emails,
        "skipped_emails": job.skipped_emails,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "error_log": job.error_log if job.status == JobStatus.FAILED else None,
    }


@router.get("/history/{user_id}")
async def get_email_transaction_sync_history(
    user_id: str,
    limit: int = Query(default=10, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session)
):
    jobs = (await session.execute(
        select(EmailTransactionSyncJob)
        .filter_by(user_id=user_id)
        .order_by(EmailTransactionSyncJob.created_at.desc())
        .limit(limit)
    )).scalars().all()

    return {
        "user_id": user_id,
        "total_jobs": len(jobs),
        "jobs": [
            {
                "job_id": str(job.id),
                "sync_type": "initial" if job.is_initial else "incremental",
                "status": job.status.value,
                "total_emails": job.total_emails,
                "parsed_transactions": job.parsed_transactions,
                "failed_emails": job.failed_emails,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "created_at": job.created_at.isoformat()
            }
            for job in jobs
        ]
    }


@router.get("/stats")
async def get_email_transaction_sync_stats(session: AsyncSession = Depends(get_db_session)):
    jobs = (await session.execute(select(EmailTransactionSyncJob))).scalars().all()

    return {
        "total_jobs": len(jobs),
        "by_status": {
            "processing": sum(1 for j in jobs if j.status == JobStatus.PROCESSING),
            "completed": sum(1 for j in jobs if j.status == JobStatus.COMPLETED),
            "failed": sum(1 for j in jobs if j.status == JobStatus.FAILED),
        },
        "total_emails_processed": sum(j.processed_emails for j in jobs),
        "total_transactions_parsed": sum(j.parsed_transactions for j in jobs),
        "total_failed_emails": sum(j.failed_emails for j in jobs),
    }
