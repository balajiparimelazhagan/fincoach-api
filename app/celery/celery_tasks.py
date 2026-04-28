from datetime import datetime, timedelta
from typing import List
import asyncio

from celery.utils.log import get_task_logger
from app.celery.celery_app import celery_app
from app.models import Transaction, EmailTransactionSyncJob
from app.models.user import User
from app.celery.celery_db import CeleryAsyncSessionLocal as AsyncSessionLocal
from sqlalchemy import select
from app.celery.email_processing_helper import (
    fetch_user_emails_async,
    schedule_incremental_sync_async,
)
from app.celery.sms_processing_helper import process_sms_batch_async

logger = get_task_logger(__name__)


def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(None)


# ==============================================================================
# PATTERN PROCESSING
# ==============================================================================

@celery_app.task(bind=True, max_retries=2)
def update_recurring_streak(self, user_id: str, transactor_id: str, direction: str, transaction_date: str):
    async def inner():
        async with AsyncSessionLocal() as db:
            from datetime import datetime as dt
            txn_date = dt.fromisoformat(transaction_date)

            tx_result = await db.execute(
                select(Transaction).where(
                    (Transaction.user_id == user_id) &
                    (Transaction.transactor_id == transactor_id) &
                    (Transaction.type == direction) &
                    (Transaction.date == txn_date)
                ).order_by(Transaction.date.desc()).limit(1)
            )
            transaction = tx_result.scalar()

            if not transaction:
                logger.warning(f"[PATTERN] Transaction not found for user {user_id}, transactor {transactor_id}")
                return {'status': 'no_transaction'}

            try:
                from app.services.pattern_service import PatternService

                pattern_service = PatternService(db)
                result = await pattern_service.process_new_transaction(transaction.id)
                logger.info(f"[PATTERN] Processing result: {result}")
                return {
                    'status': 'processed',
                    'matched': result.get('matched', False),
                    'matches': result.get('matches', [])
                }
            except Exception as e:
                logger.error(f"[PATTERN] Error in pattern processing: {e}", exc_info=True)
                raise

    try:
        return run_async(inner())
    except Exception as e:
        logger.error(f"[PATTERN] Pattern processing failed: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=30 * (self.request.retries + 1))


# ==============================================================================
# EMAIL PROCESSING TASKS
# ==============================================================================

@celery_app.task(bind=True, max_retries=3, soft_time_limit=7200, time_limit=7800)
def fetch_user_emails_initial(self, user_id: str, months: int = 3):
    try:
        return run_async(fetch_user_emails_async(user_id, is_initial=True, months=months))
    except Exception as exc:
        logger.error(f"Initial sync failed for user {user_id}: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


@celery_app.task(bind=True, max_retries=3)
def fetch_user_emails_incremental(self, user_id: str):
    try:
        return run_async(fetch_user_emails_async(user_id, is_initial=False))
    except Exception as exc:
        logger.error(f"Incremental sync failed for user {user_id}: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


@celery_app.task
def schedule_incremental_sync():
    run_async(schedule_incremental_sync_async(fetch_user_emails_incremental))


# ==============================================================================
# SMS PROCESSING TASKS
# ==============================================================================

@celery_app.task(bind=True, max_retries=3)
def process_sms_batch_task(self, user_id: str, messages_data: List[dict]):
    try:
        return run_async(process_sms_batch_async(user_id, messages_data))
    except Exception as exc:
        logger.error(f"SMS batch task failed for user {user_id}: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


# ==============================================================================
# SPENDING ANALYSIS TASKS
# ==============================================================================

@celery_app.task(bind=True, max_retries=2, soft_time_limit=300, time_limit=360)
def analyze_spending_patterns(self, user_id: str):
    """Run deterministic pattern discovery for a single user."""
    async def inner():
        async with AsyncSessionLocal() as session:
            from app.services.pattern_service import PatternService
            import uuid
            service = PatternService(session)
            result = await service.discover_patterns_for_user(uuid.UUID(user_id))
            logger.info(f"[PATTERN_DISCOVERY] Found {len(result)} patterns for user {user_id}")
            return {"status": "success", "user_id": user_id, "patterns_found": len(result)}

    try:
        return run_async(inner())
    except Exception as exc:
        logger.error(f"Pattern analysis failed for user {user_id}: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


@celery_app.task
def schedule_spending_analysis():
    """Fan out pattern analysis to all users."""
    async def get_user_ids():
        async with AsyncSessionLocal() as session:
            users = (await session.execute(select(User))).scalars().all()
            return [str(u.id) for u in users]

    user_ids = run_async(get_user_ids())
    if not user_ids:
        return

    from celery import group
    group(analyze_spending_patterns.s(uid) for uid in user_ids).apply_async()
    logger.info(f"Scheduled spending analysis for {len(user_ids)} users")


# ==============================================================================
# CLEANUP TASKS
# ==============================================================================

@celery_app.task
def cleanup_stale_email_sync_jobs():
    async def cleanup():
        async with AsyncSessionLocal() as db:
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
                    "error": "Job marked stale (PROCESSING for >2 hours)",
                })

            if stale_jobs:
                await db.commit()
                logger.info(f"Cleaned up {len(stale_jobs)} stale email sync jobs")

            return {"cleaned_jobs": len(stale_jobs)}

    return run_async(cleanup())
