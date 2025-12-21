"""
Email Transaction Sync API endpoints for triggering and monitoring email fetch jobs.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID

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
    months: int = Query(default=3, ge=1, le=12, description="Number of months to fetch (1-12)"),
    force: bool = Query(default=False, description="Force new sync even if jobs exist"),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Trigger initial email transaction sync for a user.
    Creates separate sync jobs for each calendar month, processing from latest to oldest.
    
    Args:
        user_id: User ID to sync emails for
        months: Number of months to fetch (default: 3, max: 12)
        force: If True, will delete old non-monthly jobs and create new monthly jobs
    
    Returns:
        Task information with job IDs for each month
    """
    # Validate user exists
    user = (await session.execute(select(User).filter_by(id=user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # If force is True, delete old non-monthly jobs
    if force:
        old_jobs = (await session.execute(
            select(EmailTransactionSyncJob)
            .filter_by(user_id=user_id)
            .filter(EmailTransactionSyncJob.month_sequence.is_(None))
        )).scalars().all()
        
        if old_jobs:
            for job in old_jobs:
                await session.delete(job)
            await session.commit()
            logger.info(f"Deleted {len(old_jobs)} old non-monthly jobs for user {user_id}")
    
    # Check for any stuck processing jobs (old non-monthly jobs)
    stuck_jobs = (await session.execute(
        select(EmailTransactionSyncJob)
        .filter_by(user_id=user_id, status=JobStatus.PROCESSING)
        .filter(EmailTransactionSyncJob.month_sequence.is_(None))
    )).scalars().all()
    
    if stuck_jobs:
        return {
            "message": "Old non-monthly jobs are still processing. Use force=true to delete them and start fresh.",
            "stuck_jobs": [str(j.id) for j in stuck_jobs],
            "status": "blocked"
        }
    
    # Check if there are already initial sync jobs for this user
    existing_initial_jobs = (await session.execute(
        select(EmailTransactionSyncJob)
        .filter_by(user_id=user_id, is_initial=True)
        .filter(EmailTransactionSyncJob.month_sequence.isnot(None))
        .order_by(EmailTransactionSyncJob.created_at.desc())
    )).scalars().all()
    
    if existing_initial_jobs:
        processing_jobs = [j for j in existing_initial_jobs if j.status == JobStatus.PROCESSING]
        if processing_jobs:
            return {
                "message": "Email transaction sync already in progress",
                "job_ids": [str(j.id) for j in existing_initial_jobs],
                "status": "processing"
            }
        
        # If all initial jobs exist but are completed/failed, return them
        return {
            "message": "Initial sync jobs already exist",
            "job_ids": [str(j.id) for j in existing_initial_jobs],
            "status": "exists"
        }
    
    # Queue the task
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
    """
    Get email transaction sync status for a user.
    Shows all monthly jobs if they exist, otherwise shows the most recent job.
    
    Args:
        user_id: User ID
    
    Returns:
        Job status with progress information. If monthly jobs exist, returns all of them.
    """
    # Check for monthly initial jobs first
    monthly_jobs = (await session.execute(
        select(EmailTransactionSyncJob)
        .filter_by(user_id=user_id, is_initial=True)
        .filter(EmailTransactionSyncJob.month_sequence.isnot(None))
        .order_by(EmailTransactionSyncJob.month_sequence.asc())
    )).scalars().all()
    
    if monthly_jobs:
        # Return status of all monthly jobs
        jobs_status = []
        for job in monthly_jobs:
            jobs_status.append({
                "job_id": str(job.id),
                "month_sequence": job.month_sequence,
                "month_start": job.month_start_date.isoformat() if job.month_start_date else None,
                "month_end": job.month_end_date.isoformat() if job.month_end_date else None,
                "status": job.status.value,
                "progress": round(job.progress_percentage, 2),
                "total_emails": job.total_emails,
                "processed_emails": job.processed_emails,
                "parsed_transactions": job.parsed_transactions,
                "failed_emails": job.failed_emails,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            })
        
        # Calculate overall progress
        total_jobs = len(monthly_jobs)
        completed_jobs = sum(1 for j in monthly_jobs if j.status == JobStatus.COMPLETED)
        processing_jobs = sum(1 for j in monthly_jobs if j.status == JobStatus.PROCESSING)
        
        return {
            "sync_type": "monthly_batched",
            "overall_progress": round((completed_jobs / total_jobs) * 100, 2),
            "total_months": total_jobs,
            "completed_months": completed_jobs,
            "processing_months": processing_jobs,
            "jobs": jobs_status
        }
    
    # Fall back to most recent job
    job = (await session.execute(
        select(EmailTransactionSyncJob)
        .filter_by(user_id=user_id)
        .order_by(EmailTransactionSyncJob.created_at.desc())
    )).scalar_one_or_none()
    
    if not job:
        return {
            "status": "not_started",
            "message": "No email transaction sync jobs found for this user"
        }
    
    return {
        "sync_type": "single",
        "job_id": str(job.id),
        "status": job.status.value,
        "progress": round(job.progress_percentage, 2),
        "total_emails": job.total_emails,
        "processed_emails": job.processed_emails,
        "parsed_transactions": job.parsed_transactions,
        "failed_emails": job.failed_emails,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "error_log": job.error_log if job.status == JobStatus.FAILED else None
    }


@router.get("/history/{user_id}")
async def get_email_transaction_sync_history(
    user_id: str,
    limit: int = Query(default=10, ge=1, le=100, description="Number of jobs to return"),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Get email transaction sync job history for a user.
    
    Args:
        user_id: User ID
        limit: Maximum number of jobs to return (default: 10, max: 100)
    
    Returns:
        List of past sync jobs
    """
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
                "status": job.status.value,
                "progress": round(job.progress_percentage, 2),
                "total_emails": job.total_emails,
                "processed_emails": job.processed_emails,
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
    """
    Get overall email transaction sync statistics.
    
    Returns:
        Aggregated statistics across all users
    """
    # Get counts by status
    total_jobs = (await session.execute(select(EmailTransactionSyncJob))).scalars().all()
    
    stats = {
        "total_jobs": len(total_jobs),
        "by_status": {
            "pending": len([j for j in total_jobs if j.status == JobStatus.PENDING]),
            "processing": len([j for j in total_jobs if j.status == JobStatus.PROCESSING]),
            "completed": len([j for j in total_jobs if j.status == JobStatus.COMPLETED]),
            "failed": len([j for j in total_jobs if j.status == JobStatus.FAILED]),
        },
        "total_emails_processed": sum(j.processed_emails for j in total_jobs),
        "total_transactions_parsed": sum(j.parsed_transactions for j in total_jobs),
        "total_failed_emails": sum(j.failed_emails for j in total_jobs),
    }
    
    return stats


@router.delete("/cleanup/{user_id}")
async def cleanup_old_jobs(
    user_id: str,
    session: AsyncSession = Depends(get_db_session)
):
    """
    Delete old non-monthly sync jobs for a user.
    Useful for cleaning up jobs created before the monthly batching feature.
    
    Args:
        user_id: User ID to clean up jobs for
    
    Returns:
        Number of jobs deleted
    """
    # Validate user exists
    user = (await session.execute(select(User).filter_by(id=user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Find old non-monthly jobs
    old_jobs = (await session.execute(
        select(EmailTransactionSyncJob)
        .filter_by(user_id=user_id)
        .filter(EmailTransactionSyncJob.month_sequence.is_(None))
    )).scalars().all()
    
    if not old_jobs:
        return {
            "message": "No old jobs found",
            "deleted_count": 0
        }
    
    # Delete them
    deleted_count = len(old_jobs)
    for job in old_jobs:
        await session.delete(job)
    
    await session.commit()
    
    logger.info(f"Deleted {deleted_count} old non-monthly jobs for user {user_id}")
    
    return {
        "message": f"Successfully deleted {deleted_count} old job(s)",
        "deleted_count": deleted_count,
        "deleted_job_ids": [str(j.id) for j in old_jobs]
    }
