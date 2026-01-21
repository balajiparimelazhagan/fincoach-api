"""
Transaction Handler Service for async processing.

When a new transaction is created, queue streak update tasks asynchronously.
impl_2.md: Task B (streak updates) must be triggered on EVERY transaction.
"""

from app.models.transaction import Transaction
from app.logging_config import get_logger

logger = get_logger(__name__)


async def handle_new_transaction(transaction: Transaction) -> None:
    """
    Called right after a transaction is persisted to database.
    Queues async streak update task.
    
    Args:
        transaction: The newly created Transaction object
    
    Returns:
        None (async task queued, no blocking)
    """
    # Import here to avoid circular dependency
    from app.celery.celery_tasks import update_recurring_streak
    
    try:
        # Queue streak update task asynchronously
        # impl_2.md: Task B runs on EVERY transaction
        update_recurring_streak.delay(
            user_id=str(transaction.user_id),
            transactor_id=str(transaction.transactor_id),
            direction=transaction.type,  # DEBIT or CREDIT
            transaction_date=transaction.date.isoformat()
        )
        logger.debug(f"Queued streak update for txn {transaction.id}, "
                    f"user {transaction.user_id}, transactor {transaction.transactor_id}")
    except Exception as e:
        logger.error(f"Failed to queue streak update for transaction {transaction.id}: {e}")
        # Don't raise - streak update failure should not block transaction creation
        # Retry will happen on next schedule
