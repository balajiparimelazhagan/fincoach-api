from celery.utils.log import get_task_logger
from datetime import datetime, timedelta, timezone
from typing import List
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError

from app.celery.celery_db import CeleryAsyncSessionLocal as AsyncSessionLocal
from app.services.transaction_handler import handle_new_transaction
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

BATCH_SIZE = 100


async def fetch_user_emails_async(user_id: str, is_initial: bool = False, months: int = 3):
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).filter_by(id=user_id))).scalar_one_or_none()
        if not user:
            logger.error(f"User {user_id} not found")
            return {"status": "error", "message": "User not found"}

        if not user.google_token_pickle and not user.google_credentials_json:
            logger.info(f"User {user_id} has no Gmail credentials, skipping sync")
            return {"status": "skipped", "message": "No Gmail credentials"}

        existing_job = (await session.execute(
            select(EmailTransactionSyncJob).filter_by(user_id=user_id, status=JobStatus.PROCESSING)
        )).scalar_one_or_none()
        if existing_job:
            logger.info(f"Sync already in-progress for user {user_id}, skipping (job: {existing_job.id})")
            return {"status": "skipped", "message": "Another sync job is already processing"}

        job = EmailTransactionSyncJob(
            user_id=user_id,
            status=JobStatus.PROCESSING,
            is_initial=is_initial,
            started_at=datetime.utcnow(),
        )
        session.add(job)
        try:
            await session.commit()
            await session.refresh(job)
        except IntegrityError:
            await session.rollback()
            return {"status": "skipped", "message": "Concurrent job already processing"}

        try:
            fetcher = GmailService(
                credentials_data=user.google_credentials_json,
                token_data=user.google_token_pickle
            )
            coordinator = EmailProcessingCoordinator()

            if is_initial:
                since_date = datetime.now(timezone.utc) - timedelta(days=months * 30)
            else:
                max_lookback = datetime.now(timezone.utc) - timedelta(days=settings.EMAIL_FETCH_DAYS)
                since_date = (
                    user.last_email_fetch_time
                    if user.last_email_fetch_time and user.last_email_fetch_time > max_lookback
                    else max_lookback
                )

            logger.info(f"{'Initial' if is_initial else 'Incremental'} sync for user {user_id}: fetching since {since_date}")

            all_emails = fetcher.fetch_bank_emails(
                since_date=since_date,
                ascending=settings.EMAIL_FETCH_ASCENDING,
                max_results=None
            )

            job.total_emails = len(all_emails)
            await session.commit()

            if not all_emails:
                logger.info(f"No new emails for user {user_id}")
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.utcnow()
                await session.commit()
                return {"status": "success", "message": "No new emails"}

            logger.info(f"Found {len(all_emails)} emails for user {user_id}. Processing in batches...")

            for i in range(0, len(all_emails), BATCH_SIZE):
                batch = all_emails[i:i + BATCH_SIZE]
                await process_email_batch(session, batch, coordinator, user_id, job)
                await session.commit()  # persist job stats after each batch
                logger.info(f"Progress: {job.processed_emails}/{job.total_emails} for user {user_id}")

            # Update last_email_fetch_time to the latest email seen
            email_dates = [e[3] for e in all_emails if len(e) >= 4 and isinstance(e[3], datetime)]
            if email_dates:
                latest = max(email_dates)
                if user.last_email_fetch_time is None or latest > user.last_email_fetch_time:
                    user.last_email_fetch_time = latest

            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.utcnow()
            await session.commit()

            logger.info(f"Completed sync for user {user_id}: {job.parsed_transactions} transactions from {job.total_emails} emails")

            return {
                "status": "success",
                "total_emails": job.total_emails,
                "parsed_transactions": job.parsed_transactions,
                "failed_emails": job.failed_emails,
            }

        except Exception as e:
            logger.error(f"Error processing emails for user {user_id}: {e}", exc_info=True)
            await session.refresh(job)
            job.status = JobStatus.FAILED
            job.completed_at = datetime.utcnow()
            if job.error_log is None:
                job.error_log = []
            job.error_log.append({
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e),
                "error_type": type(e).__name__,
            })
            await session.commit()
            raise


async def process_email_batch(session, emails: List, coordinator: EmailProcessingCoordinator, user_id: str, job: EmailTransactionSyncJob):
    # Accumulate stats in local vars — ORM object state resets on rollback
    batch_parsed = 0
    batch_failed = 0
    batch_skipped = 0
    batch_processed = 0
    batch_errors = []

    for email_item in emails:
        message_id = None
        subject = None
        batch_processed += 1

        try:
            message_id, subject, body = email_item[:3]
            sender_email = email_item[4] if len(email_item) > 4 else None

            result = coordinator.process_email(message_id, subject, body, sender_email)

            if not result.processed:
                batch_skipped += 1
                continue

            transaction = result.transaction
            if not transaction:
                batch_failed += 1
                continue

            # Category
            category = (await session.execute(
                select(Category).filter_by(label=transaction.category)
            )).scalar_one_or_none()
            if not category:
                category = Category(label=transaction.category)
                session.add(category)
                await session.flush()

            # Transactor
            transactor = None
            if transaction.transactor_source_id:
                transactor = (await session.execute(
                    select(Transactor).filter_by(source_id=transaction.transactor_source_id, user_id=user_id)
                )).scalar_one_or_none()
            if not transactor and transaction.transactor:
                transactor = (await session.execute(
                    select(Transactor).filter_by(name=transaction.transactor, user_id=user_id)
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
                transactor.source_id = transaction.transactor_source_id

            # Currency (default INR)
            currency = (await session.execute(
                select(Currency).filter_by(value="INR")
            )).scalar_one_or_none()
            if not currency:
                currency = Currency(name="Indian Rupee", value="INR", country="India")
                session.add(currency)
                await session.flush()

            # Account
            account = None
            if transaction.account_last_four:
                account = await get_or_create_account(
                    session=session,
                    user_id=user_id,
                    account_last_four=transaction.account_last_four,
                    bank_name=transaction.bank_name or "Unknown",
                    account_type=getattr(transaction, 'account_type', 'savings')
                )

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
                account_id=account.id if account else None,
            )
            session.add(db_transaction)
            await session.commit()

            await handle_new_transaction(db_transaction)
            batch_parsed += 1

        except IntegrityError:
            await session.rollback()
            batch_skipped += 1
            logger.debug(f"Duplicate transaction for message_id {message_id}, skipping")

        except Exception as e:
            await session.rollback()
            batch_failed += 1
            batch_errors.append({
                "message_id": message_id,
                "subject": subject[:100] if subject else "",
                "error": str(e),
                "error_type": type(e).__name__,
            })
            logger.error(f"Error processing email {message_id}: {e}", exc_info=True)

    # Apply batch stats to job once (caller commits)
    job.parsed_transactions += batch_parsed
    job.failed_emails += batch_failed
    job.skipped_emails += batch_skipped
    job.processed_emails += batch_processed
    if batch_errors:
        if job.error_log is None:
            job.error_log = []
        job.error_log.extend(batch_errors)


async def schedule_incremental_sync_async(fetch_user_emails_incremental_task):
    async with AsyncSessionLocal() as session:
        users = (await session.execute(select(User))).scalars().all()
        if not users:
            return

        tasks = []
        for user in users:
            if not user.google_token_pickle and not user.google_credentials_json:
                continue

            existing_job = (await session.execute(
                select(EmailTransactionSyncJob).filter_by(user_id=user.id, status=JobStatus.PROCESSING)
            )).scalars().first()

            if existing_job:
                logger.info(f"Skipping incremental sync for user {user.id}: job {existing_job.id} already processing")
                continue

            tasks.append(fetch_user_emails_incremental_task.s(str(user.id)))

        if tasks:
            from celery import group
            group(tasks).apply_async()

        logger.info(f"Scheduled incremental sync for {len(tasks)} users")
