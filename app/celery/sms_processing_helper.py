"""
SMS processing helper functions for Celery tasks.
Contains core async logic for SMS transaction extraction and processing.
"""
from celery.utils.log import get_task_logger
from datetime import datetime
from typing import List
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError

from app.db import AsyncSessionLocal
from app.models.user import User
from app.models.sms_transaction_sync_job import SmsTransactionSyncJob, JobStatus as SmsJobStatus
from app.models.transaction import Transaction as DBTransaction
from app.models.category import Category
from app.models.transactor import Transactor
from app.models.currency import Currency
from agent.coordinator import SmsProcessingCoordinator

logger = get_task_logger(__name__)


async def process_sms_batch_async(user_id: str, messages_data: List[dict]):
    """Core async logic for SMS transaction batch processing"""
    async with AsyncSessionLocal() as session:
        # Get user
        user = (await session.execute(select(User).filter_by(id=user_id))).scalar_one_or_none()
        if not user:
            logger.error(f"User {user_id} not found")
            return {"status": "error", "message": "User not found"}
        
        # Create SMS transaction sync job
        job = SmsTransactionSyncJob(
            user_id=user_id,
            status=SmsJobStatus.PROCESSING,
            started_at=datetime.utcnow(),
            total_sms=len(messages_data)
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        
        try:
            # Initialize coordinator
            coordinator = SmsProcessingCoordinator()
            
            if not messages_data:
                logger.info(f"No SMS transaction messages for user {user_id}")
                job.status = SmsJobStatus.COMPLETED
                job.completed_at = datetime.utcnow()
                job.progress_percentage = 100.0
                await session.commit()
                return {"status": "success", "message": "No SMS transaction messages"}
            
            logger.info(f"Processing {len(messages_data)} SMS transaction messages for user {user_id}")
            
            # Process each SMS
            await process_sms_messages(session, messages_data, coordinator, user_id, job)
            
            # Mark job complete
            job.status = SmsJobStatus.COMPLETED
            job.completed_at = datetime.utcnow()
            job.progress_percentage = 100.0
            
            await session.commit()
            
            logger.info(
                f"✅ Completed SMS transaction sync for user {user_id}: "
                f"{job.parsed_transactions} transactions parsed from {job.total_sms} SMS messages"
            )
            
            return {
                "status": "success",
                "total_sms": job.total_sms,
                "parsed_transactions": job.parsed_transactions,
                "failed_sms": job.failed_sms,
                "skipped_sms": job.skipped_sms
            }
        
        except Exception as e:
            logger.error(f"Error processing SMS transactions for user {user_id}: {e}", exc_info=True)
            job.status = SmsJobStatus.FAILED
            if job.error_log is None:
                job.error_log = []
            job.error_log.append({"timestamp": datetime.utcnow().isoformat(), "error": str(e)})
            await session.commit()
            raise


async def process_sms_messages(
    session, 
    messages_data: List[dict], 
    coordinator: SmsProcessingCoordinator, 
    user_id: str, 
    job: SmsTransactionSyncJob
):
    """Process a batch of SMS transaction messages using A2A coordination and save transactions"""
    
    for msg_data in messages_data:
        sms_id = None
        sender = None
        
        try:
            # Extract SMS data
            sms_id = msg_data["sms_id"]
            body = msg_data["body"]
            sender = msg_data["sender"]
            timestamp_str = msg_data.get("timestamp")
            
            # Parse timestamp
            timestamp = None
            if timestamp_str:
                try:
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                except Exception:
                    timestamp = datetime.utcnow()
            else:
                timestamp = datetime.utcnow()
            
            # Process SMS with A2A coordination
            result = coordinator.process_sms(
                sms_id=sms_id,
                sms_body=body,
                sender=sender,
                timestamp=timestamp
            )
            
            # Check if SMS was processed
            if not result.processed:
                job.skipped_sms += 1
                logger.info(f"Skipped SMS from {sender}: {body[:50]}... - Reason: {result.skip_reason}")
                continue
            
            # Get transaction from result
            transaction = result.transaction
            
            if not transaction:
                job.failed_sms += 1
                logger.warning(f"Failed to extract transaction from SMS: {body[:50]}...")
                continue
            
            # Check for duplicate by sms_id (reuse message_id field)
            existing = (await session.execute(
                select(DBTransaction).filter_by(message_id=sms_id)
            )).scalar_one_or_none()
            
            if existing:
                logger.debug(f"Skipping duplicate transaction for sms_id: {sms_id}")
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
                    name=transaction.transactor or sender or "Unknown",
                    source_id=transaction.transactor_source_id,
                    user_id=user_id
                )
                session.add(transactor)
                await session.flush()
            elif transaction.transactor_source_id and not transactor.source_id:
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
                message_id=sms_id  # Store SMS ID in message_id field
            )
            session.add(db_transaction)
            
            # Commit immediately after each transaction
            await session.commit()
            
            job.parsed_transactions += 1
            logger.info(
                f"✓ Committed SMS transaction: {transaction.amount} {transaction.transaction_type.value} "
                f"- {transaction.description[:50]}"
            )
            
        except IntegrityError as e:
            # Duplicate sms_id - this SMS was already processed
            await session.rollback()
            logger.debug(f"Skipping duplicate transaction for sms_id {sms_id}")
            continue
            
        except Exception as e:
            # Any other error - rollback and continue with next SMS
            await session.rollback()
            logger.error(f"Error processing SMS {sms_id}: {e}", exc_info=True)
            job.failed_sms += 1
            if job.error_log is None:
                job.error_log = []
            job.error_log.append({
                "sms_id": sms_id,
                "sender": sender,
                "error": str(e)
            })
            continue
        
        # Update progress
        job.processed_sms += 1
        job.progress_percentage = (job.processed_sms / job.total_sms) * 100
        await session.commit()
    
    # Final commit for job progress updates
    try:
        await session.commit()
        logger.info(
            f"✅ SMS transaction batch processing complete: {job.parsed_transactions} transactions, "
            f"{job.failed_sms} failed, {job.skipped_sms} skipped"
        )
    except Exception as e:
        logger.error(f"Failed to commit final SMS transaction job progress: {e}", exc_info=True)
        await session.rollback()
