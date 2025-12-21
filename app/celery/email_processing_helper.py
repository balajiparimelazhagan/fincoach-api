"""
Email processing helper functions for Celery tasks.
Contains core async logic for email fetching and transaction extraction.
"""
from celery.utils.log import get_task_logger
from datetime import datetime, timedelta, timezone, date
from typing import List, Tuple
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified
from calendar import monthrange

from app.db import AsyncSessionLocal
from app.models.user import User
from app.models.email_transaction_sync_job import EmailTransactionSyncJob, JobStatus
from app.models.transaction import Transaction as DBTransaction
from app.models.category import Category
from app.models.transactor import Transactor
from app.models.currency import Currency
from app.models.account import Account
from app.services.google.mail import GmailService
from app.services.account_service import get_or_create_account
from agent.coordinator import EmailProcessingCoordinator
from app.config import settings

logger = get_task_logger(__name__)

BATCH_SIZE = 100  # Process 100 emails at a time


def calculate_monthly_ranges(num_months: int = 3) -> List[Tuple[date, date, int]]:
    """
    Calculate calendar month ranges for batched processing.
    Returns list of (start_date, end_date, sequence) tuples from latest to oldest.
    
    Args:
        num_months: Number of months to generate (default: 3)
    
    Returns:
        List of tuples: [(month1_start, month1_end, 1), (month2_start, month2_end, 2), ...]
        Month 1 is the current month, Month 2 is previous month, etc.
        
    Example: If today is Dec 20, 2025:
        [(date(2025, 12, 1), date(2025, 12, 20), 1),
         (date(2025, 11, 1), date(2025, 11, 30), 2),
         (date(2025, 10, 1), date(2025, 10, 31), 3)]
    """
    today = date.today()
    ranges = []
    
    for i in range(num_months):
        # Calculate target month
        target_month = today.month - i
        target_year = today.year
        
        # Handle year rollover
        while target_month <= 0:
            target_month += 12
            target_year -= 1
        
        # Start is always the 1st of the month
        month_start = date(target_year, target_month, 1)
        
        # End is either today (for current month) or last day of month
        if i == 0:
            # Current month: use today as end date
            month_end = today
        else:
            # Past months: use last day of that month
            last_day = monthrange(target_year, target_month)[1]
            month_end = date(target_year, target_month, last_day)
        
        ranges.append((month_start, month_end, i + 1))
    
    return ranges


async def create_monthly_sync_jobs(user_id: str, num_months: int = 3) -> List[str]:
    """
    Create separate sync jobs for each calendar month.
    Jobs are created in sequence from latest to oldest.
    
    Args:
        user_id: User ID to create jobs for
        num_months: Number of months to create jobs for (default: 3)
    
    Returns:
        List of job IDs created
    """
    async with AsyncSessionLocal() as session:
        # Check if initial sync jobs already exist for this user
        existing_initial_jobs = (await session.execute(
            select(EmailTransactionSyncJob).filter_by(user_id=user_id, is_initial=True)
        )).scalars().all()
        
        if existing_initial_jobs:
            logger.info(f"Initial monthly sync jobs already exist for user {user_id}")
            return [str(job.id) for job in existing_initial_jobs]
        
        monthly_ranges = calculate_monthly_ranges(num_months)
        jobs = []
        
        for month_start, month_end, sequence in monthly_ranges:
            job = EmailTransactionSyncJob(
                user_id=user_id,
                status=JobStatus.PENDING,
                is_initial=True,
                month_start_date=month_start,
                month_end_date=month_end,
                month_sequence=sequence,
                created_at=datetime.utcnow()
            )
            session.add(job)
            jobs.append(job)
            logger.info(f"Creating sync job for user {user_id}, month {sequence}: {month_start} to {month_end}")
        
        await session.commit()
        
        # Refresh to get generated IDs
        for job in jobs:
            await session.refresh(job)
        
        # Convert UUIDs to strings
        job_ids = [str(job.id) for job in jobs]
        
        logger.info(f"Created {len(job_ids)} monthly sync jobs for user {user_id}")
        return job_ids


async def trigger_next_monthly_job(session, user_id: str, completed_sequence: int):
    """
    Trigger the next monthly sync job after completing the current one.
    
    Args:
        session: Database session
        user_id: User ID
        completed_sequence: Sequence number of the just-completed job
    """
    # Find the next pending monthly job for this user
    next_job = (await session.execute(
        select(EmailTransactionSyncJob)
        .filter_by(
            user_id=user_id,
            is_initial=True,
            status=JobStatus.PENDING
        )
        .filter(EmailTransactionSyncJob.month_sequence > completed_sequence)
        .order_by(EmailTransactionSyncJob.month_sequence.asc())
    )).scalars().first()
    
    if next_job:
        logger.info(f"Triggering next monthly job (sequence {next_job.month_sequence}) for user {user_id}")
        
        # Import here to avoid circular dependency
        from app.celery.celery_tasks import process_monthly_email_job
        
        # Trigger the next job
        process_monthly_email_job.delay(str(user_id), str(next_job.id))
    else:
        logger.info(f"All monthly sync jobs completed for user {user_id}")


async def fetch_user_emails_async(user_id: str, job_id: str = None):
    """
    Core async logic for email fetching and transaction extraction.
    
    Fetches emails from Gmail, processes them through A2A coordination pipeline,
    and creates transaction records in the database.
    
    Args:
        user_id: UUID string of the user to fetch emails for
        job_id: Optional job ID to process. If provided, will process that specific monthly job.
                If not provided, performs incremental sync from last fetch time.
    
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
        
        # If job_id is provided, fetch that specific job
        if job_id:
            job = (await session.execute(
                select(EmailTransactionSyncJob).filter_by(id=job_id)
            )).scalar_one_or_none()
            
            if not job:
                logger.error(f"Job {job_id} not found")
                return {"status": "error", "message": "Job not found"}
            
            # Check if job is already processing
            if job.status == JobStatus.PROCESSING:
                logger.info(f"Job {job_id} is already processing")
                return {"status": "skipped", "message": "Job already processing"}
            
            # Update job status to processing
            job.status = JobStatus.PROCESSING
            job.started_at = datetime.utcnow()
            await session.commit()
            
        else:
            # Incremental sync path: Guard against concurrent jobs
            existing_job = (await session.execute(
                select(EmailTransactionSyncJob).filter_by(user_id=user_id, status=JobStatus.PROCESSING)
            )).scalar_one_or_none()
            if existing_job:
                logger.info(f"Sync already in-progress for user {user_id}, skipping new job creation (job: {existing_job.id}).")
                return {"status": "skipped", "message": "Another sync job is already processing"}

            # Create incremental sync job
            job = EmailTransactionSyncJob(
                user_id=user_id,
                status=JobStatus.PROCESSING,
                started_at=datetime.utcnow(),
                is_initial=False
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
            if job.is_initial and job.month_start_date and job.month_end_date:
                # Monthly batched sync: use job's month boundaries
                since_date = datetime.combine(job.month_start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
                until_date = datetime.combine(job.month_end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
                logger.info(f"Monthly batch sync for user {user_id}, month {job.month_sequence}: {job.month_start_date} to {job.month_end_date}")
                
                # Fetch emails for this month
                all_emails = fetcher.fetch_bank_emails(
                    since_date=since_date,
                    until_date=until_date,
                    ascending=settings.EMAIL_FETCH_ASCENDING, 
                    max_results=None
                )
            else:
                # Incremental sync: fetch from last fetch time or max lookback period
                max_lookback_date = datetime.now(timezone.utc) - timedelta(days=settings.EMAIL_FETCH_DAYS)
                
                if user.last_email_fetch_time and user.last_email_fetch_time > max_lookback_date:
                    since_date = user.last_email_fetch_time
                    logger.info(f"Incremental email transaction sync for user {user_id}: fetching since last fetch time {since_date}")
                else:
                    since_date = max_lookback_date
                    logger.info(f"Incremental email transaction sync for user {user_id}: no recent fetch time, using max lookback of {settings.EMAIL_FETCH_DAYS} days from {since_date}")
                
                # Fetch emails since last sync
                all_emails = fetcher.fetch_bank_emails(
                    since_date=since_date, 
                    ascending=settings.EMAIL_FETCH_ASCENDING, 
                    max_results=None
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
            
            # Initialize processed_message_ids tracking
            if job.processed_message_ids is None:
                job.processed_message_ids = {}
            
            # Process emails in batches to manage memory and commit progress incrementally
            for i in range(0, len(all_emails), BATCH_SIZE):
                batch = all_emails[i:i + BATCH_SIZE]
                await process_email_batch(session, batch, coordinator, user_id, job)
                
                # Refresh job from DB to get latest state
                await session.refresh(job)
                
                # Calculate progress from processed_message_ids (exact count)
                job.processed_emails = len(job.processed_message_ids)
                job.progress_percentage = (job.processed_emails / job.total_emails) * 100 if job.total_emails > 0 else 100.0
                
                await session.commit()
                
                logger.info(f"Progress: {job.processed_emails}/{job.total_emails} ({job.progress_percentage:.1f}%) for user {user_id}")
            
            # Mark job complete
            await session.refresh(job)
            job.processed_emails = len(job.processed_message_ids)
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.utcnow()
            job.progress_percentage = 100.0
            
            # Clear processed_message_ids to save space (keep counts for stats)
            job.processed_message_ids = None
            
            # Update last fetch time only for incremental syncs (not for monthly initial syncs)
            if not job.is_initial:
                # Update last fetch time to the latest email date to enable incremental fetching
                if all_emails:
                    try:
                        email_dates = [e[3] for e in all_emails if len(e) >= 4 and isinstance(e[3], datetime)]
                        if email_dates:
                            user.last_email_fetch_time = max(email_dates)
                    except Exception:
                        # Keep existing last_email_fetch_time on parse errors
                        logger.warning(f"Failed to compute latest email date for user {user_id}, keeping previous last_email_fetch_time: {user.last_email_fetch_time}")
            
            await session.commit()
            
            logger.info(f"✅ Completed email transaction sync for user {user_id}: {job.parsed_transactions} transactions parsed from {job.total_emails} emails")
            
            # If this was a monthly job, trigger the next month
            if job.is_initial and job.month_sequence:
                await trigger_next_monthly_job(session, user_id, job.month_sequence)
            
            return {
                "status": "success",
                "total_emails": job.total_emails,
                "parsed_transactions": job.parsed_transactions,
                "failed_emails": job.failed_emails
            }
        
        except Exception as e:
            # Log error and mark job as failed
            logger.error(f"Error processing emails for user {user_id}: {e}", exc_info=True)
            
            await session.refresh(job)
            job.status = JobStatus.FAILED
            job.completed_at = datetime.utcnow()
            
            if job.error_log is None:
                job.error_log = []
            job.error_log.append({
                "timestamp": datetime.utcnow().isoformat(), 
                "error": str(e),
                "traceback": str(type(e).__name__)
            })
            
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
        - Refreshes job from DB periodically to detect external changes
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
    
    emails_processed_in_batch = 0
    
    # Initialize processed_message_ids if needed
    if job.processed_message_ids is None:
        job.processed_message_ids = {}
    
    for email_item in emails:
        message_id = None
        subject = None
        
        try:
            # Extract email data (includes sender email as 5th element)
            message_id, subject, body = email_item[:3]
            sender_email = email_item[4] if len(email_item) > 4 else None
            
            # Check if already processed (idempotency)
            if message_id in job.processed_message_ids:
                logger.debug(f"Skipping already processed email: {message_id}")
                emails_processed_in_batch += 1
                continue
            
            # Process email with A2A coordination (Intent Classifier -> Transaction Extractor -> Account Extractor)
            result = coordinator.process_email(message_id, subject, body, sender_email)
            
            emails_processed_in_batch += 1
            
            # Check if email was processed
            if not result.processed:
                job.skipped_emails += 1
                # Mark as processed even if skipped (informational/promotional emails don't need retry)
                job.processed_message_ids[message_id] = True
                job.processed_emails = len(job.processed_message_ids)
                flag_modified(job, "processed_message_ids")
                await session.commit()  # Commit JSONB update
                logger.info(f"Skipped email: {subject[:50]}... - Reason: {result.skip_reason}")
                continue
            
            # Get transaction from result
            transaction = result.transaction
            
            if not transaction:
                job.failed_emails += 1
                logger.warning(f"Failed to extract transaction: {subject[:50]}...")
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
            
            # Get or create Account from transaction data (already extracted by coordinator)
            account = None
            if transaction.account_last_four:
                account = await get_or_create_account(
                    session=session,
                    user_id=user_id,
                    account_last_four=transaction.account_last_four,
                    bank_name=transaction.bank_name or "Unknown",
                    account_type=getattr(transaction, 'account_type', 'savings')
                )
            
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
                message_id=message_id,
                account_id=account.id if account else None
            )
            session.add(db_transaction)
            
            # Commit transaction immediately
            await session.commit()
            
            # Mark as successfully processed and update progress
            job.processed_message_ids[message_id] = True
            job.parsed_transactions += 1
            job.processed_emails = len(job.processed_message_ids)
            
            # Flag JSONB as modified for SQLAlchemy
            flag_modified(job, "processed_message_ids")
            
            # Commit the JSONB update immediately
            await session.commit()
            
        except IntegrityError as e:
            # Duplicate message_id - this email was already processed in transactions table
            # Mark as processed to avoid retrying
            await session.rollback()
            job.processed_message_ids[message_id] = True
            job.skipped_emails += 1
            job.processed_emails = len(job.processed_message_ids)
            flag_modified(job, "processed_message_ids")
            await session.commit()  # Commit JSONB update
            logger.debug(f"Skipping duplicate transaction for message_id {message_id}")
            continue
            
        except Exception as e:
            # Any other error - rollback and continue with next email
            # DO NOT mark as processed - allow retry on next job run
            await session.rollback()
            logger.error(f"Error processing email {message_id}: {e}", exc_info=True)
            job.failed_emails += 1
            
            if job.error_log is None:
                job.error_log = []
            job.error_log.append({
                "message_id": message_id,
                "subject": subject[:100] if subject else "",
                "error": str(e),
                "error_type": type(e).__name__
            })
            
            continue
    
    # Final commit for job progress updates
    await session.commit()
    logger.info(f"✅ Batch processing complete: {job.parsed_transactions} transactions, {job.failed_emails} failed")


async def schedule_incremental_sync_async(fetch_user_emails_incremental_task):
    """
    Schedule incremental sync for users who have completed their initial monthly batches.
    
    Excludes:
    - Users with pending/processing monthly jobs (is_initial=true)
    - Users already running an incremental sync
    
    Args:
        fetch_user_emails_incremental_task: Celery task signature for incremental fetch
    """
    async with AsyncSessionLocal() as session:
        users = (await session.execute(select(User))).scalars().all()
        
        if not users:
            logger.info("No users found for incremental sync")
            return
        
        tasks = []
        max_runtime_hours = getattr(settings, "EMAIL_SYNC_JOB_MAX_RUNTIME_HOURS", 6)
        
        for user in users:
            # Check for any pending or processing monthly jobs (initial sync not complete)
            monthly_job = (await session.execute(
                select(EmailTransactionSyncJob).filter_by(
                    user_id=user.id, 
                    is_initial=True
                ).filter(
                    EmailTransactionSyncJob.status.in_([JobStatus.PENDING, JobStatus.PROCESSING])
                )
            )).scalars().first()
            
            if monthly_job:
                logger.info(f"Skipping incremental sync for user {user.id}: still processing monthly batches (job {monthly_job.id})")
                continue
            
            # Check for existing incremental job
            existing_job = (await session.execute(
                select(EmailTransactionSyncJob).filter_by(user_id=user.id, status=JobStatus.PROCESSING)
            )).scalars().first()
            
            if existing_job:
                # If the job started too long ago, mark it failed/stale
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
                else:
                    logger.info(f"Skipping scheduling incremental sync for user {user.id}: job {existing_job.id} already processing")
                    continue
            
            tasks.append(fetch_user_emails_incremental_task.s(str(user.id)))

        if tasks:
            from celery import group
            task_group = group(tasks)
            task_group.apply_async()
        
        logger.info(f"Scheduled incremental sync for {len(tasks)} users")
