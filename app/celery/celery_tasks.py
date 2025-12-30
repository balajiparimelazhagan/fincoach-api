
from datetime import datetime, timedelta
from app.models.spending_analysis_job import SpendingAnalysisJob
from app.models.email_transaction_sync_job import EmailTransactionSyncJob
from app.celery.celery_app import celery_app
from app.services.spending_analysis_service import SpendingAnalysisService
from app.services.streak_service import StreakService

from app.models import RecurringPattern, Transaction, Transactor, User, RecurringPatternStreak
from agent.spending_analysis_coordinator import SpendingAnalysisCoordinator
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import AsyncSessionLocal
from sqlalchemy import select
import asyncio
from celery.utils.log import get_task_logger


# ==============================================================================
# TASK A: PATTERN DETECTION (Nightly / On Threshold)
# LLM-based pattern discovery - creates or updates recurring patterns
# ==============================================================================

@celery_app.task(bind=True, max_retries=3)
def detect_or_update_recurring_pattern(self, user_id: str, job_id: str):
    """
    Task A: Detect or update recurring patterns for a user.
    
    impl_2.md: Pattern detection = "What kind of recurring behavior is this?"
    - Triggered nightly or on threshold
    - Calls LLM (expensive, rare)
    - Creates recurring_patterns table entries
    - Initializes recurring_pattern_streaks if new pattern
    
    DO NOT:
    - Backfill streak from history
    - Recompute streak here
    - Override streak data
    """
    def _run():
        async def inner():
            logger = get_task_logger(__name__)
            logger.info(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
            logger.info(f"[TASK-A] Starting pattern detection for user {user_id}, job {job_id}")
            async with AsyncSessionLocal() as db:
                service = SpendingAnalysisService(db)
                tx_result = await db.execute(
                    select(Transaction, Transactor)
                    .join(Transactor, Transaction.transactor_id == Transactor.id)
                    .where(Transaction.user_id == user_id)
                )
                tx_rows = tx_result.all()
                logger.info("========================================================")
                logger.info(f"[TASK-A] Fetched {len(tx_rows)} transactions for user {user_id}")
                
                # Group by (transactor_id, direction) - impl_2.md: DEBIT and CREDIT always separate
                transactor_direction_map = {}
                for tx, transactor in tx_rows:
                    # Direction from transaction type (DEBIT/CREDIT)
                    direction = tx.type or 'DEBIT'  # Default to DEBIT if missing
                    key = (str(transactor.id), direction)
                    
                    if key not in transactor_direction_map:
                        transactor_direction_map[key] = {
                            "transactor_id": str(transactor.id),
                            "transactor_name": transactor.name,
                            "direction": direction,
                            "transactions": []
                        }
                    transactor_direction_map[key]["transactions"].append({
                        "date": tx.date,
                        "amount": tx.amount
                    })
                
                coordinator = SpendingAnalysisCoordinator()
                total_analyzed = 0
                patterns_detected = 0
                errors = []
                
                # Analyze each (transactor, direction) separately
                for (transactor_id, direction), transactor_data in transactor_direction_map.items():
                    try:
                        pattern_result = coordinator.analyze_transactor_patterns(
                            transactor_id=transactor_data["transactor_id"],
                            transactor_name=transactor_data["transactor_name"],
                            direction=direction,
                            transactions=transactor_data["transactions"],
                            min_occurrences=3

                        )
                        total_analyzed += 1
                        logger.info(f"[TASK-A] Analyzed transactor {transactor_data['transactor_name']}: {pattern_result}")
                        if pattern_result.pattern_detected:
                            patterns_detected += 1
                            # Check if pattern already exists for this (user, transactor, direction)
                            existing_pattern_result = await db.execute(
                                select(RecurringPattern).where(
                                    (RecurringPattern.user_id == user_id) &
                                    (RecurringPattern.transactor_id == pattern_result.transactor_id) &
                                    (RecurringPattern.direction == direction)
                                )
                            )
                            existing_pattern = existing_pattern_result.scalar()
                            
                            if existing_pattern:
                                # Update only if pattern_type meaningfully changed
                                if existing_pattern.pattern_type != pattern_result.pattern_type:
                                    existing_pattern.pattern_type = pattern_result.pattern_type
                                    existing_pattern.interval_days = pattern_result.interval_days or 30
                                    existing_pattern.confidence = pattern_result.confidence
                                    existing_pattern.last_evaluated_at = datetime.utcnow()
                                    logger.info(f"[TASK-A] Updated pattern for {transactor_data['transactor_name']}")
                            else:
                                # Create new pattern with base confidence
                                pattern = RecurringPattern(
                                    user_id=user_id,
                                    transactor_id=pattern_result.transactor_id,
                                    pattern_type=pattern_result.pattern_type,
                                    interval_days=pattern_result.interval_days or 30,
                                    amount_behavior=getattr(pattern_result, 'amount_behavior', 'VARIABLE'),
                                    confidence=pattern_result.confidence,
                                    direction=direction,  # From transactor_data
                                    detected_at=datetime.utcnow(),
                                    last_evaluated_at=datetime.utcnow(),
                                    status='ACTIVE'
                                )
                                db.add(pattern)
                                await db.flush()  # Get pattern ID
                                
                                # Initialize streak for new pattern with multiplier = 1.0 (identity)
                                last_txn_date = transactor_data["transactions"][-1]["date"]
                                streak = RecurringPatternStreak(
                                    recurring_pattern_id=pattern.id,
                                    current_streak_count=1,
                                    longest_streak_count=1,
                                    last_actual_date=last_txn_date,
                                    last_expected_date=last_txn_date + timedelta(days=pattern_result.interval_days or 30),
                                    missed_count=0,
                                    confidence_multiplier=1.0,
                                    updated_at=datetime.utcnow()
                                )
                                db.add(streak)
                                logger.info(f"[TASK-A] Created pattern + streak for {transactor_data['transactor_name']}")
                            
                            await db.commit()
                        # Update job after each transactor
                        await db.execute(
                            SpendingAnalysisJob.__table__.update()
                            .where(SpendingAnalysisJob.id == job_id)
                            .values(
                                status='PROCESSING',
                                updated_at=datetime.utcnow()
                            )
                        )
                        await db.commit()
                    except Exception as e:
                        logger.error(f"[TASK-A] Error analyzing transactor {transactor_data['transactor_name']}: {e}")
                        errors.append(f"{transactor_data['transactor_name']}: {str(e)}")
                        await db.execute(
                            SpendingAnalysisJob.__table__.update()
                            .where(SpendingAnalysisJob.id == job_id)
                            .values(
                                error_message=str(e),
                                updated_at=datetime.utcnow()
                            )
                        )
                        await db.commit()
                # Final job update
                await db.execute(
                    SpendingAnalysisJob.__table__.update()
                    .where(SpendingAnalysisJob.id == job_id)
                    .values(
                        status='SUCCESS',
                        finished_at=datetime.utcnow(),
                        is_locked=False,
                        updated_at=datetime.utcnow()
                    )
                )
                await db.commit()
                logger.info(f"[TASK-A] Completed pattern detection for user {user_id}, job {job_id}")
                return {'job_id': job_id, 'status': 'SUCCESS', 'patterns_detected': patterns_detected}
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
                    .values(
                        status='FAILED',
                        is_locked=False,
                        error_message=str(e),
                        finished_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                )
                await db.commit()
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        loop.run_until_complete(_fail())
        return {'job_id': job_id, 'status': 'FAILED', 'error': str(e)}


# ==============================================================================
# TASK B: STREAK UPDATE (On Every Transaction)
# Pure code - no LLM, no pattern changes, just state machine
# ==============================================================================

@celery_app.task(bind=True, max_retries=2)
def update_recurring_streak(self, user_id: str, transactor_id: str, direction: str, transaction_date: str):
    """
    Task B: Update streak on new transaction.
    
    impl_2.md: Streak tracking = "Is this behavior still holding?"
    - Triggered on EVERY transaction
    - Pure code, NO LLM
    - Updates recurring_pattern_streaks only
    - State machine: on-time → confidence +, late → confidence -, broken → confidence drops
    
    DO NOT:
    - Call LLM
    - Reclassify pattern
    - Delete pattern on single miss
    """
    def _run():
        async def inner():
            logger = get_task_logger(__name__)
            logger.info(f"[TASK-B] Updating streak for user {user_id}, transactor {transactor_id}, direction {direction}")
            async with AsyncSessionLocal() as db:
                # Fetch pattern for this (user, transactor, direction)
                pattern_result = await db.execute(
                    select(RecurringPattern).where(
                        (RecurringPattern.user_id == user_id) &
                        (RecurringPattern.transactor_id == transactor_id) &
                        (RecurringPattern.direction == direction) &
                        (RecurringPattern.status == 'ACTIVE')
                    )
                )
                pattern = pattern_result.scalar()
                
                if not pattern:
                    logger.info(f"[TASK-B] No active pattern for user {user_id}, transactor {transactor_id} - exiting silently")
                    return {'status': 'no_pattern'}
                
                # Fetch streak
                streak_result = await db.execute(
                    select(RecurringPatternStreak).where(
                        RecurringPatternStreak.recurring_pattern_id == pattern.id
                    )
                )
                streak = streak_result.scalar()
                
                if not streak:
                    logger.warning(f"[TASK-B] Pattern exists but no streak for pattern {pattern.id}")
                    return {'status': 'no_streak'}
                
                # Use StreakService to update state
                service = StreakService(db)
                interval_days = pattern.interval_days or 30  # Default monthly
                
                try:
                    from datetime import datetime as dt
                    from decimal import Decimal
                    txn_date = dt.fromisoformat(transaction_date)
                    updated_streak = await service.update_streak_for_transaction(
                        pattern_id=pattern.id,
                        transaction_date=txn_date,
                        interval_days=interval_days,
                        tolerance_days=5
                    )
                    
                    # impl_2.md: Update pattern's final confidence = base * multiplier
                    if updated_streak:
                        base_confidence = float(pattern.confidence)
                        multiplier = float(updated_streak.confidence_multiplier)
                        final_confidence = base_confidence * multiplier
                        # Clamp to [0, 1]
                        final_confidence = max(0.0, min(1.0, final_confidence))
                        pattern.confidence = Decimal(str(final_confidence))
                        pattern.last_evaluated_at = dt.utcnow()
                    
                    await db.commit()
                    logger.info(f"[TASK-B] Updated streak for pattern {pattern.id}: "
                               f"count={updated_streak.current_streak_count}, "
                               f"multiplier={updated_streak.confidence_multiplier}, "
                               f"final_confidence={pattern.confidence}")
                    return {'status': 'updated', 'pattern_id': str(pattern.id), 'final_confidence': float(pattern.confidence)}
                except Exception as e:
                    logger.error(f"[TASK-B] Error updating streak: {e}")
                    await db.rollback()
                    raise
        
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(inner())
    
    try:
        return _run()
    except Exception as e:
        logger = get_task_logger(__name__)
        logger.error(f"[TASK-B] Streak update failed: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=30 * (self.request.retries + 1))


# ==============================================================================
# LEGACY: Scheduled pattern detection (uses Task A)
# ==============================================================================


@celery_app.task
def schedule_spending_analysis():
    """
    Periodic task to schedule pattern detection for all users (Celery Beat).
    Triggers Task A: detect_or_update_recurring_pattern
    """
    logger = get_task_logger(__name__)
    logger.info("[SCHEDULE] Starting scheduled pattern detection for all users")
    async def inner():
        async with AsyncSessionLocal() as db:
            users_result = await db.execute(select(User.id))
            user_ids = [row[0] for row in users_result.fetchall()]
            logger.info(f"[SCHEDULE] Scheduling pattern detection for {len(user_ids)} users")
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
                    logger.info(f"[SCHEDULE] Skipping user {user_id}: job already running or pending.")
                    continue
                service = SpendingAnalysisService(db)
                job = await service.create_job(user_id, triggered_by="SCHEDULED")
                logger.info(f"[SCHEDULE] Created job {job.id} for user {user_id}")
                detect_or_update_recurring_pattern.delay(str(user_id), str(job.id))
                logger.info(f"[SCHEDULE] Enqueued Task A for user {user_id}, job {job.id}")
        
    try:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(inner())
    except Exception as e:
        logger = get_task_logger(__name__)
        logger.error(f"[SCHEDULE] Pattern detection scheduling failed: {e}", exc_info=True)
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


@celery_app.task
def cleanup_stale_email_sync_jobs():
    """
    Periodic task to clean up stale email sync jobs stuck in PROCESSING state.
    If a job has been in PROCESSING for more than 2 hours, mark it as FAILED.
    This prevents jobs from being stuck forever if a worker crashes mid-processing.
    """
    async def cleanup():
        from datetime import timedelta
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

