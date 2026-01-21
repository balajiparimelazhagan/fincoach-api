"""
Celery tasks for fincoach API.

Tasks included:
- Pattern processing (new transactions)
- Email transaction sync
- SMS transaction sync
"""
from datetime import datetime, timedelta
from typing import List
import asyncio

from celery.utils.log import get_task_logger
from app.celery.celery_app import celery_app
from app.models import Transaction, EmailTransactionSyncJob
from app.db import AsyncSessionLocal
from sqlalchemy import select
from app.celery.email_processing_helper import (
    fetch_user_emails_async, 
    schedule_incremental_sync_async,
    create_monthly_sync_jobs
)
from app.celery.sms_processing_helper import process_sms_batch_async


logger = get_task_logger(__name__)


# ==============================================================================
# PATTERN PROCESSING (On Every Transaction)
# Deterministic obligation matching and pattern state updates
# ==============================================================================

@celery_app.task(bind=True, max_retries=2)
def update_recurring_streak(self, user_id: str, transactor_id: str, direction: str, transaction_date: str):
    """
    Process new transaction against active patterns.
    
    DETERMINISTIC SYSTEM:
    - Matches transactions against pattern obligations
    - Updates pattern state (fulfill/miss obligations)
    - Advances streaks on successful match
    - Pure code, NO LLM
    
    Args:
        user_id: User ID
        transactor_id: Transactor ID
        direction: DEBIT or CREDIT
        transaction_date: ISO format transaction date
    """
    logger.info(f"[CELERY_TASK] update_recurring_streak triggered: user={user_id}, transactor={transactor_id}, direction={direction}")
    
    def _run():
        async def inner():
            logger.info(f"[PATTERN] Processing transaction for user {user_id}, transactor {transactor_id}, direction {direction}")
            async with AsyncSessionLocal() as db:
                # Get the actual transaction to process against patterns
                from datetime import datetime as dt
                txn_date = dt.fromisoformat(transaction_date)
                
                tx_result = await db.execute(
                    select(Transaction).where(
                        (Transaction.user_id == user_id) &
                        (Transaction.transactor_id == transactor_id) &
                        (Transaction.type == direction) &
                        (Transaction.date == txn_date)
                    ).order_by(Transaction.created_at.desc()).limit(1)
                )
                transaction = tx_result.scalar()
                
                if not transaction:
                    logger.warning(f"[PATTERN] Transaction not found for user {user_id}, transactor {transactor_id}")
                    return {'status': 'no_transaction'}
                
                # Process with deterministic pattern service
                try:
                    from app.services.pattern_service import PatternService
                    from sqlalchemy.orm import Session
                    
                    # Create sync session from async
                    sync_db = Session(bind=db.sync_connection())
                    pattern_service = PatternService(sync_db)
                    
                    result = pattern_service.process_new_transaction(transaction.id)
                    logger.info(f"[PATTERN] Processing result: {result}")
                    
                    return {
                        'status': 'processed',
                        'matched': result.get('matched', False),
                        'matches': result.get('matches', [])
                    }
                except Exception as e:
                    logger.error(f"[PATTERN] Error in pattern processing: {e}", exc_info=True)
                    return {'status': 'error', 'error': str(e)}
        
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(inner())
    
    try:
        return _run()
    except Exception as e:
        logger.error(f"[PATTERN] Pattern processing failed: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=30 * (self.request.retries + 1))


# ==============================================================================
# EMAIL PROCESSING TASKS
# ==============================================================================

@celery_app.task(bind=True, max_retries=3)
def fetch_user_emails_initial(self, user_id: str, months: int = 3):
    """
    Initial bulk fetch for a new user (creates 3 monthly batch jobs)
    
    Args:
        user_id: User ID
        months: Number of months to fetch (default 3, creates separate jobs per month)
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    try:
        # Create monthly sync jobs
        job_ids = loop.run_until_complete(create_monthly_sync_jobs(user_id, months))
        
        # Trigger the first month's job (sequence 1)
        if job_ids:
            process_monthly_email_job.delay(user_id, job_ids[0])
            
        return {"status": "success", "job_ids": job_ids, "message": f"Created {len(job_ids)} monthly sync jobs"}
    except Exception as exc:
        logger.error(f"Task failed for user {user_id}: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


@celery_app.task(bind=True, max_retries=3, soft_time_limit=7200, time_limit=7800)
def process_monthly_email_job(self, user_id: str, job_id: str):
    """
    Process a specific monthly email sync job
    
    Args:
        user_id: User ID
        job_id: Job ID to process
        
    Time limits:
        - soft_time_limit: 7200s (2 hours) - raises SoftTimeLimitExceeded
        - time_limit: 7800s (130 min) - hard kill
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    try:
        logger.info(f"Starting monthly job {job_id} for user {user_id}")
        result = loop.run_until_complete(fetch_user_emails_async(user_id, job_id=job_id))
        logger.info(f"Completed monthly job {job_id} for user {user_id}: {result}")
        return result
    except Exception as exc:
        logger.error(f"Monthly job {job_id} failed for user {user_id}: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


@celery_app.task(bind=True, max_retries=3)
def fetch_user_emails_incremental(self, user_id: str):
    """
    Incremental fetch for existing users (since last sync)
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    try:
        return loop.run_until_complete(fetch_user_emails_async(user_id))
    except Exception as exc:
        logger.error(f"Incremental sync failed for user {user_id}: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


@celery_app.task
def schedule_incremental_sync():
    """
    Periodic task to sync emails for all users
    Run this every 30 minutes via Celery Beat
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    loop.run_until_complete(schedule_incremental_sync_async(fetch_user_emails_incremental))


# ==============================================================================
# SMS PROCESSING TASKS
# ==============================================================================

@celery_app.task(bind=True, max_retries=3)
def process_sms_batch_task(self, user_id: str, messages_data: List[dict]):
    """
    Process a batch of SMS messages from mobile app
    
    Args:
        user_id: User ID
        messages_data: List of SMS message dicts with keys: sms_id, body, sender, timestamp
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    try:
        return loop.run_until_complete(process_sms_batch_async(user_id, messages_data))
    except Exception as exc:
        logger.error(f"SMS batch task failed for user {user_id}: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


# ==============================================================================
# CLEANUP TASKS
# ==============================================================================

@celery_app.task
def cleanup_stale_email_sync_jobs():
    """
    Periodic task to clean up stale email sync jobs stuck in PROCESSING state.
    If a job has been in PROCESSING for more than 2 hours, mark it as FAILED.
    This prevents jobs from being stuck forever if a worker crashes mid-processing.
    """
    async def cleanup():
        async with AsyncSessionLocal() as db:
            # Find jobs in PROCESSING state for more than 2 hours
            stale_threshold = datetime.utcnow() - timedelta(hours=2)
            
            result = await db.execute(
                select(EmailTransactionSyncJob)
                .where(EmailTransactionSyncJob.status == 'processing')
                .where(EmailTransactionSyncJob.started_at < stale_threshold)
            )
            stale_jobs = result.scalars().all()
            
            for job in stale_jobs:
                logger.warning(f"Marking stale job {job.id} as FAILED (started {job.started_at})")
                job.status = 'failed'
                job.completed_at = datetime.utcnow()
                if job.error_log is None:
                    job.error_log = []
                job.error_log.append({
                    "timestamp": datetime.utcnow().isoformat(),
                    "error": "Job marked as stale (in PROCESSING for >2 hours)",
                    "traceback": "cleanup_stale_email_sync_jobs"
                })
            
            if stale_jobs:
                await db.commit()
                logger.info(f"Cleaned up {len(stale_jobs)} stale email sync jobs")
            
            return {"cleaned_jobs": len(stale_jobs)}
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(cleanup())
