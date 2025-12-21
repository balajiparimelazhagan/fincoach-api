"""
Celery tasks for email and SMS transaction processing.
Background workers process these tasks asynchronously.
"""
from celery.utils.log import get_task_logger
from typing import List
import asyncio

from app.celery.celery_app import celery_app
from app.celery.email_processing_helper import (
    fetch_user_emails_async, 
    schedule_incremental_sync_async,
    create_monthly_sync_jobs
)
from app.celery.sms_processing_helper import process_sms_batch_async

logger = get_task_logger(__name__)


# ============================================================================
# EMAIL PROCESSING TASKS
# ============================================================================

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


@celery_app.task(bind=True, max_retries=3, soft_time_limit=3600, time_limit=3900)
def process_monthly_email_job(self, user_id: str, job_id: str):
    """
    Process a specific monthly email sync job
    
    Args:
        user_id: User ID
        job_id: Job ID to process
        
    Time limits:
        - soft_time_limit: 3600s (1 hour) - raises SoftTimeLimitExceeded
        - time_limit: 3900s (65 min) - hard kill
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


# ============================================================================
# SMS PROCESSING TASKS
# ============================================================================

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
