"""
Email processing helper functions for Celery tasks.
Contains core async logic for email fetching and transaction extraction.
"""
from celery.utils.log import get_task_logger
from datetime import datetime, timedelta, timezone
from typing import List
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError

from app.db import AsyncSessionLocal
from app.models.user import User
from app.models.email_transaction_sync_job import EmailTransactionSyncJob, JobStatus
from app.models.transaction import Transaction as DBTransaction
from app.models.category import Category
from app.models.transactor import Transactor
from app.models.currency import Currency
from app.services.google.mail import GmailService
from agent.coordinator import EmailProcessingCoordinator
from app.config import settings

logger = get_task_logger(__name__)

BATCH_SIZE = 100  # Process 100 emails at a time


async def fetch_user_emails_async(user_id: str, months: int = 6, is_initial: bool = True):
    """
    Core async logic for email fetching and transaction extraction.
    
    Fetches emails from Gmail, processes them through A2A coordination pipeline,
    and creates transaction records in the database.
    
    Args:
        user_id: UUID string of the user to fetch emails for
        months: Number of months to look back for initial sync (default: 6)
        is_initial: If True, performs initial sync for specified months.
                   If False, performs incremental sync from last fetch time.
    
    Returns:
        Dict containing status and details:
        - status: "success", "error", or "skipped"
        - message: Status message if skipped/error
        - total_emails: Number of emails processed (on success)
        - parsed_transactions: Number of transactions created (on success)
        - failed_emails: Number of emails that failed processing (on success)
    
    Raises:
        Exception: Re-raises any processing errors after marking job as failed
    """
    async with AsyncSessionLocal() as session:
        # Get user
        user = (await session.execute(select(User).filter_by(id=user_id))).scalar_one_or_none()
        if not user:
            logger.error(f"User {user_id} not found")
            return {"status": "error", "message": "User not found"}
        
        # Guard: avoid creating a new job if there's already one processing for the user
        existing_job = (await session.execute(
            select(EmailTransactionSyncJob).filter_by(user_id=user_id, status=JobStatus.PROCESSING)
        )).scalar_one_or_none()
        if existing_job:
            logger.info(f"Sync already in-progress for user {user_id}, skipping new job creation (job: {existing_job.id}).")
            return {"status": "skipped", "message": "Another sync job is already processing"}

        # Create sync job; if a concurrent job exists, the DB unique constraint will prevent duplicates
        job = EmailTransactionSyncJob(
            user_id=user_id,
            status=JobStatus.PROCESSING,
            started_at=datetime.utcnow()
        )
        session.add(job)
        try:
            await session.commit()
            await session.refresh(job)
        except IntegrityError:
            # Another job was created concurrently (race); roll back and skip
            await session.rollback()
            logger.info(f"Another processing job already present for user {user_id}, skipping this worker invocation.")
            return {"status": "skipped", "message": "Concurrent job already processing"}
        
        try:
            # Initialize fetcher and parser
            fetcher = GmailService(
                credentials_data=user.google_credentials_json,
                token_data=user.google_token_pickle
            )
            coordinator = EmailProcessingCoordinator()
            
            # Determine date range based on sync type
            if is_initial:
                # Initial sync: fetch specified months of historical data
                since_date = datetime.now(timezone.utc) - timedelta(days=months * 30)
                logger.info(f"Initial email transaction sync for user {user_id}: fetching {months} months from {since_date}")
            else:
                # Incremental sync: fetch from last fetch time or max lookback period
                # Calculate max lookback date based on EMAIL_FETCH_DAYS setting
                max_lookback_date = datetime.now(timezone.utc) - timedelta(days=settings.EMAIL_FETCH_DAYS)
                
                if user.last_email_fetch_time and user.last_email_fetch_time > max_lookback_date:
                    since_date = user.last_email_fetch_time
                    logger.info(f"Incremental email transaction sync for user {user_id}: fetching since last fetch time {since_date}")
                else:
                    since_date = max_lookback_date
                    logger.info(f"Incremental email transaction sync for user {user_id}: no recent fetch time, using max lookback of {settings.EMAIL_FETCH_DAYS} days from {since_date}")
            
            # Fetch emails in streaming manner
            all_emails = fetcher.fetch_bank_emails(
                since_date=since_date, 
                ascending=settings.EMAIL_FETCH_ASCENDING, 
                max_results=None  # Fetch all available
            )
            
            job.total_emails = len(all_emails)
            await session.commit()
            
            # Handle case where no emails are found
            if not all_emails:
                logger.info(f"No new emails for user {user_id}")
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.utcnow()
                job.progress_percentage = 100.0
                await session.commit()
                return {"status": "success", "message": "No new emails"}
            
            logger.info(f"Found {len(all_emails)} emails for user {user_id}. Processing in batches...")
            
            # Process emails in batches to manage memory and commit progress incrementally
            for i in range(0, len(all_emails), BATCH_SIZE):
                batch = all_emails[i:i + BATCH_SIZE]
                await process_email_batch(session, batch, coordinator, user_id, job)
                
                # Update progress after each batch
                job.processed_emails += len(batch)
                job.progress_percentage = (job.processed_emails / job.total_emails) * 100
                await session.commit()
                
                logger.info(f"Progress: {job.processed_emails}/{job.total_emails} ({job.progress_percentage:.1f}%) for user {user_id}")
            
            # Mark job complete
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.utcnow()
            
            # Update last fetch time to the latest email date to enable incremental fetching
            if all_emails:
                try:
                    email_dates = [e[3] for e in all_emails if len(e) >= 4 and isinstance(e[3], datetime)]
                    if email_dates:
                        user.last_email_fetch_time = max(email_dates)
                    # if we don't have valid email dates, keep the previous last_email_fetch_time to avoid skipping older emails
                except Exception:
                    # Keep existing last_email_fetch_time on parse errors
                    logger.warning(f"Failed to compute latest email date for user {user_id}, keeping previous last_email_fetch_time: {user.last_email_fetch_time}")
            
            await session.commit()
            
            logger.info(f"✅ Completed email transaction sync for user {user_id}: {job.parsed_transactions} transactions parsed from {job.total_emails} emails")
            
            return {
                "status": "success",
                "total_emails": job.total_emails,
                "parsed_transactions": job.parsed_transactions,
                "failed_emails": job.failed_emails
            }
        
        except Exception as e:
            # Log error, mark job as failed, and re-raise to be handled by Celery
            logger.error(f"Error processing emails for user {user_id}: {e}", exc_info=True)
            job.status = JobStatus.FAILED
            if job.error_log is None:
                job.error_log = []
            job.error_log.append({"timestamp": datetime.utcnow().isoformat(), "error": str(e)})
            await session.commit()
            raise


async def process_email_batch(session, emails: List, coordinator: EmailProcessingCoordinator, user_id: str, job: EmailTransactionSyncJob):
    """
    Process a batch of emails and extract financial transactions.
    This function iterates through a list of emails, uses AI coordination to extract
    transaction information, and saves valid transactions to the database. It handles
    duplicate detection, creates related entities (categories, transactors, currencies),
    and tracks processing statistics.
    Args:
        session: SQLAlchemy async session for database operations
        emails (List): List of email tuples containing (message_id, subject, body, ...)
        coordinator (EmailProcessingCoordinator): A2A coordinator for intent classification 
            and transaction extraction
        user_id (str): ID of the user who owns these transactions
        job (EmailTransactionSyncJob): Job object to track processing statistics and errors
    Returns:
        None: Updates the job object in-place with processing statistics
    Processing Flow:
        1. Extract email data (message_id, subject, body)
        2. Process email through A2A coordination (Intent Classifier -> Transaction Extractor)
        3. Skip non-transaction emails or already processed emails
        4. Create or fetch related entities:
            - Category (based on transaction category)
            - Transactor (by source_id or name, creates if not exists)
            - Currency (defaults to INR)
        5. Create DBTransaction record with extracted data
        6. Commit transaction immediately after creation
        7. Update job statistics (parsed_transactions, failed_emails, skipped_emails)
    Error Handling:
        - IntegrityError: Skips duplicate transactions (by message_id)
        - Other exceptions: Rolls back, logs error, continues with next email
        - Error details are appended to job.error_log
    Side Effects:
        - Creates database records for transactions, categories, transactors, and currencies
        - Updates job object statistics and error log
        - Commits after each successful transaction
        - Logs processing progress and errors
    Note:
        Each transaction is committed individually to ensure partial success even if
        later emails fail to process. This prevents losing all progress on batch failure.
    """
    """Process a batch of emails using A2A coordination and save transactions"""
    
    for email_item in emails:
        message_id = None
        subject = None
        
        try:
            # Extract email data
            message_id, subject, body = email_item[:3]
            
            # Process email with A2A coordination (Intent Classifier -> Transaction Extractor)
            result = coordinator.process_email(message_id, subject, body)
            
            # Check if email was processed
            if not result.processed:
                job.skipped_emails += 1
                logger.info(f"Skipped email: {subject[:50]}... - Reason: {result.skip_reason}")
                continue
            
            # Get transaction from result
            transaction = result.transaction
            
            if not transaction:
                job.failed_emails += 1
                logger.warning(f"Failed to extract transaction: {subject[:50]}...")
                continue
            
            # Check if transaction with this message_id already exists (avoid duplicate processing)
            existing = (await session.execute(
                select(DBTransaction).filter_by(message_id=message_id)
            )).scalar_one_or_none()
            
            if existing:
                logger.debug(f"Skipping duplicate transaction for message_id: {message_id}")
                continue
            
            # Get or create Category
            category = (await session.execute(
                select(Category).filter_by(label=transaction.category)
            )).scalar_one_or_none()
            
            if not category:
                category = Category(label=transaction.category)
                session.add(category)
                await session.flush()
            
            # Get or create Transactor
            # First try to find by source_id if provided, otherwise by name
            transactor = None
            if transaction.transactor_source_id:
                transactor = (await session.execute(
                    select(Transactor).filter_by(
                        source_id=transaction.transactor_source_id, 
                        user_id=user_id
                    )
                )).scalar_one_or_none()
            
            if not transactor and transaction.transactor:
                transactor = (await session.execute(
                    select(Transactor).filter_by(
                        name=transaction.transactor, 
                        user_id=user_id
                    )
                )).scalar_one_or_none()
            
            if not transactor:
                transactor = Transactor(
                    name=transaction.transactor or "Unknown",
                    source_id=transaction.transactor_source_id,
                    user_id=user_id
                )
                session.add(transactor)
                await session.flush()
            elif transaction.transactor_source_id and not transactor.source_id:
                # Update existing transactor with source_id if not already set
                transactor.source_id = transaction.transactor_source_id
                await session.flush()
            
            # Get Currency (default INR)
            currency = (await session.execute(
                select(Currency).filter_by(value="INR")
            )).scalar_one_or_none()
            
            if not currency:
                currency = Currency(name="Indian Rupee", value="INR", country="India")
                session.add(currency)
                await session.flush()
            
            # Create transaction
            db_transaction = DBTransaction(
                amount=transaction.amount,
                type=transaction.transaction_type.value,
                date=datetime.strptime(transaction.date, "%Y-%m-%d %H:%M:%S"),
                description=transaction.description,
                confidence=str(transaction.confidence),
                user_id=user_id,
                category_id=category.id,
                transactor_id=transactor.id,
                currency_id=currency.id,
                message_id=message_id
            )
            session.add(db_transaction)
            
            # Commit immediately after each transaction
            await session.commit()
            
            job.parsed_transactions += 1
            logger.info(f"✓ Committed transaction: {transaction.amount} {transaction.transaction_type.value} - {transaction.description[:50]}")
            
        except IntegrityError as e:
            # Duplicate message_id - this email was already processed
            await session.rollback()
            logger.debug(f"Skipping duplicate transaction for message_id {message_id}")
            continue
            
        except Exception as e:
            # Any other error - rollback and continue with next email
            await session.rollback()
            logger.error(f"Error processing email {message_id}: {e}", exc_info=True)
            job.failed_emails += 1
            if job.error_log is None:
                job.error_log = []
            job.error_log.append({
                "message_id": message_id,
                "subject": subject[:100] if subject else "",
                "error": str(e)
            })
            continue
    
    # Final commit for job progress updates
    try:
        await session.commit()
        logger.info(f"✅ Batch processing complete: {job.parsed_transactions} transactions, {job.failed_emails} failed")
    except Exception as e:
        logger.error(f"Failed to commit final job progress: {e}", exc_info=True)
        await session.rollback()


async def schedule_incremental_sync_async(fetch_user_emails_incremental_task):
    """
    Schedule incremental sync for all users.
    
    Args:
        fetch_user_emails_incremental_task: Celery task signature for incremental fetch
    """
    async with AsyncSessionLocal() as session:
        users = (await session.execute(select(User))).scalars().all()
        
        if not users:
            logger.info("No users found for incremental sync")
            return
        
        # Only schedule incremental sync for users that don't already have a processing job
        tasks = []
        # Determine stale job threshold (hours). If job started longer than this many hours ago, consider it stale.
        max_runtime_hours = getattr(settings, "EMAIL_SYNC_JOB_MAX_RUNTIME_HOURS", 6)
        for user in users:
            existing_job = (await session.execute(
                select(EmailTransactionSyncJob).filter_by(user_id=user.id, status=JobStatus.PROCESSING)
            )).scalar_one_or_none()
            if existing_job:
                # If the job started too long ago, mark it failed/stale and allow rescheduling
                if existing_job.started_at and (datetime.utcnow() - existing_job.started_at) > timedelta(hours=max_runtime_hours):
                    logger.warning(f"Found stale processing job {existing_job.id} for user {user.id}, started at {existing_job.started_at}. Marking as FAILED to allow new scheduling.")
                    existing_job.status = JobStatus.FAILED
                    if existing_job.error_log is None:
                        existing_job.error_log = []
                    existing_job.error_log.append({
                        "timestamp": datetime.utcnow().isoformat(),
                        "error": "Stale job detected by scheduler"
                    })
                    await session.commit()
                    existing_job = None
            if existing_job:
                logger.info(f"Skipping scheduling incremental sync for user {user.id}: job {existing_job.id} already processing")
                continue
            tasks.append(fetch_user_emails_incremental_task.s(str(user.id)))

        if tasks:
            from celery import group
            task_group = group(tasks)
            task_group.apply_async()
        
        logger.info(f"Scheduled incremental sync for {len(users)} users")
