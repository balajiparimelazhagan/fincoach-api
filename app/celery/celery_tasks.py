
from datetime import datetime
from app.models.spending_analysis_job import SpendingAnalysisJob
from app.celery.celery_app import celery_app
from app.services.spending_analysis_service import SpendingAnalysisService

from app.models import RecurringPattern, Transaction, Transactor, User
from agent.spending_analysis_coordinator import SpendingAnalysisCoordinator
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import AsyncSessionLocal
from sqlalchemy import select
import asyncio


@celery_app.task(bind=True, max_retries=3)
def analyze_spending_patterns(self, user_id: str, job_id: str):
    """
    Celery task to analyze spending patterns for a user (immediate or scheduled).
    """
    def _run():
        async def inner():
            logger = get_task_logger(__name__)
            logger.info(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
            logger.info(f"Starting spending analysis for user {user_id}, job {job_id}")
            async with AsyncSessionLocal() as db:
                service = SpendingAnalysisService(db)
                tx_result = await db.execute(
                    select(Transaction, Transactor)
                    .join(Transactor, Transaction.transactor_id == Transactor.id)
                    .where(Transaction.user_id == user_id)
                )
                tx_rows = tx_result.all()
                logger.info("========================================================")
                logger.info(f"Fetched {len(tx_rows)} transactions for user {user_id}")
                transactor_map = {}
                for tx, transactor in tx_rows:
                    if transactor.id not in transactor_map:
                        transactor_map[transactor.id] = {
                            "transactor_id": str(transactor.id),
                            "transactor_name": transactor.name,
                            "transactions": []
                        }
                    transactor_map[transactor.id]["transactions"].append({
                        "date": tx.date,
                        "amount": tx.amount
                    })
                coordinator = SpendingAnalysisCoordinator()
                total_analyzed = 0
                patterns_detected = 0
                errors = []
                for transactor_id, transactor_data in transactor_map.items():
                    try:
                        pattern_result = coordinator.analyze_transactor_patterns(
                            transactor_id=transactor_data["transactor_id"],
                            transactor_name=transactor_data["transactor_name"],
                            transactions=transactor_data["transactions"],
                            min_occurrences=3
                        )
                        total_analyzed += 1
                        logger.info(f"Analyzed transactor {transactor_data['transactor_name']}: {pattern_result}")
                        if pattern_result.pattern_detected:
                            patterns_detected += 1
                            await db.execute(
                                RecurringPattern.__table__.delete().where(
                                    (RecurringPattern.user_id == user_id) &
                                    (RecurringPattern.transactor_id == pattern_result.transactor_id)
                                )
                            )
                            pattern = RecurringPattern(
                                user_id=user_id,
                                transactor_id=pattern_result.transactor_id,
                                pattern_type=pattern_result.pattern_type,
                                frequency=pattern_result.frequency,
                                confidence=pattern_result.confidence,
                                avg_amount=pattern_result.avg_amount,
                                min_amount=pattern_result.min_amount,
                                max_amount=pattern_result.max_amount,
                                amount_variance_percent=pattern_result.amount_variance,
                                total_occurrences=pattern_result.total_occurrences,
                                occurrences_in_pattern=pattern_result.total_occurrences,
                                first_transaction_date=pattern_result.first_transaction_date,
                                last_transaction_date=pattern_result.last_transaction_date,
                                analyzed_at=pattern_result.analyzed_at if hasattr(pattern_result, 'analyzed_at') else None,
                                created_at=pattern_result.analyzed_at if hasattr(pattern_result, 'analyzed_at') else None,
                                updated_at=pattern_result.analyzed_at if hasattr(pattern_result, 'analyzed_at') else None,
                            )
                            db.add(pattern)
                            await db.commit()
                        # Update job after each transactor
                        await db.execute(
                            SpendingAnalysisJob.__table__.update()
                            .where(SpendingAnalysisJob.id == job_id)
                            .values(
                                total_transactors_analyzed=total_analyzed,
                                patterns_detected=patterns_detected,
                                updated_at=datetime.utcnow(),
                                error_log=errors
                            )
                        )
                        await db.commit()
                    except Exception as e:
                        logger.error(f"Error analyzing transactor {transactor_data['transactor_name']}: {e}")
                        errors.append(f"{transactor_data['transactor_name']}: {str(e)}")
                        await db.execute(
                            SpendingAnalysisJob.__table__.update()
                            .where(SpendingAnalysisJob.id == job_id)
                            .values(
                                total_transactors_analyzed=total_analyzed,
                                patterns_detected=patterns_detected,
                                updated_at=datetime.utcnow(),
                                error_log=errors
                            )
                        )
                        await db.commit()
                # Final job update
                await db.execute(
                    SpendingAnalysisJob.__table__.update()
                    .where(SpendingAnalysisJob.id == job_id)
                    .values(
                        status='COMPLETED',
                        completed_at=datetime.utcnow(),
                        is_locked=False,
                        updated_at=datetime.utcnow(),
                        total_transactors_analyzed=total_analyzed,
                        patterns_detected=patterns_detected,
                        error_log=errors
                    )
                )
                await db.commit()
                logger.info(f"Completed spending analysis for user {user_id}, job {job_id}")
                return {'job_id': job_id, 'status': 'COMPLETED'}
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(inner())
    try:
        return _run()
    except Exception as e:
        async def _fail():
            async with AsyncSessionLocal() as db:
                await db.execute(
                    SpendingAnalysisJob.__table__.update()
                    .where(SpendingAnalysisJob.id == job_id)
                    .values(status='FAILED', is_locked=False, updated_at=datetime.utcnow(), error_log=[str(e)])
                )
                await db.commit()
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        loop.run_until_complete(_fail())
        return {'job_id': job_id, 'status': 'FAILED', 'error': str(e)}


@celery_app.task
def schedule_spending_analysis():
    """
    Periodic task to schedule spending analysis for all users (to be run by Celery Beat).
    """
    logger = get_task_logger(__name__)
    logger.info("[SpendingAnalysis] Starting scheduled spending analysis for all users")
    async def inner():
        async with AsyncSessionLocal() as db:
            users_result = await db.execute(select(User.id))
            user_ids = [row[0] for row in users_result.fetchall()]
            logger.info(f"[SpendingAnalysis] Scheduling jobs for {len(user_ids)} users")
            for user_id in user_ids:
                job_result = await db.execute(
                    select(SpendingAnalysisJob)
                    .where(
                        (SpendingAnalysisJob.user_id == user_id) &
                        (SpendingAnalysisJob.status.in_(["PENDING", "PROCESSING"]))
                    )
                )
                existing_job = job_result.scalar()
                if existing_job:
                    logger.info(f"[SpendingAnalysis] Skipping user {user_id}: job already running or pending.")
                    continue
                service = SpendingAnalysisService(db)
                job = await service.create_job(user_id, triggered_by="SCHEDULED")
                logger.info(f"[SpendingAnalysis] Created job {job.id} for user {user_id}")
                analyze_spending_patterns.delay(str(user_id), str(job.id))
                logger.info(f"[SpendingAnalysis] Enqueued analyze_spending_patterns for user {user_id}, job {job.id}")
        
    try:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(inner())
    except Exception as e:
        logger = get_task_logger(__name__)
        logger.error(f"[SpendingAnalysis] schedule_spending_analysis failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}
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
