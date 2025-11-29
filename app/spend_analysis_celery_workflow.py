import sqlalchemy.pool
import re
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict
from uuid import UUID
from collections import defaultdict

import sqlalchemy as sa
from sqlalchemy import select, update, text, or_
from sqlalchemy.ext.asyncio import AsyncSession

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Celery Configuration ---
# Assuming your Celery app instance is defined in app.celery_app
# You might need to adjust the import based on your project structure
from app.celery_app import celery_app
from app.models.transaction import Transaction
from app.models.spend_analysis import SpendAnalysis
from app.models.user import User
from app.models.category import Category
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# --- Database Configuration ---
# Ensure this matches your project's database configuration
DATABASE_URL = "postgresql+asyncpg://postgres:root@db/postgres"

Base = None  # Centralized in app.db and models

# --- Helper Functions ---

def extract_vendor(description: str) -> Optional[str]:
    """Basic vendor extraction for non-UPI descriptions."""
    common_vendors = ["Netflix", "Spotify", "Amazon", "Apple", "Google", "Microsoft", "Hulu", "Gym", "Rent"]
    for vendor in common_vendors:
        if re.search(r'\b' + re.escape(vendor) + r'\b', description, re.IGNORECASE):
            return vendor
    match = re.match(r'(\w+)', description)
    if match:
        return match.group(1).capitalize()
    return None

def normalize_upi_vendor(description: str) -> Optional[str]:
    """Attempt to derive a stable vendor/payee key from UPI style descriptions.

    Heuristics:
    - If pattern contains 'UPI', look for 'TO <name>' or 'TO:<name>' capturing words before a reference token.
    - Remove trailing reference / UTR / numeric tokens and common noise words (PAYMENT, UPI, TXN, REF, UTR, NO, ID).
    - If a VPA (virtual payment address) like 'name@bank' is present, take the part before '@'.
    - Collapse multiple spaces, title-case the result.
    Returns None if no reasonable vendor could be derived.
    """
    if 'upi' not in description.lower():
        return None

    desc = description.strip()
    # Try TO <name>
    m_to = re.search(r'\bTO[:\s]+([^\n\r]+)', desc, re.IGNORECASE)
    candidate = None
    if m_to:
        candidate = m_to.group(1)
    else:
        # Try VPA pattern
        m_vpa = re.search(r'([A-Za-z0-9_.-]+)@([A-Za-z0-9_.-]+)', desc)
        if m_vpa:
            candidate = m_vpa.group(1)

    if not candidate:
        # Fall back to removing leading 'UPI' token and taking next word sequence
        m_generic = re.search(r'upi[^A-Za-z0-9]*([A-Za-z][A-Za-z &]{2,40})', desc, re.IGNORECASE)
        if m_generic:
            candidate = m_generic.group(1)

    if not candidate:
        return None

    # Remove reference/id numbers & noise tokens
    candidate = re.sub(r'\b(REF|TXN|UTR|PAYMENT|UPI|NO|ID)\b', '', candidate, flags=re.IGNORECASE)
    candidate = re.sub(r'\b[0-9A-Z]{6,}\b', '', candidate)  # remove long alphanumerics (likely refs)
    candidate = re.sub(r'[0-9]{4,}', '', candidate)  # remove long digit sequences
    candidate = re.sub(r'[^A-Za-z &]', ' ', candidate)  # keep letters & ampersand & space
    candidate = re.sub(r'\s+', ' ', candidate).strip()
    if not candidate or len(candidate) < 2:
        return None
    return candidate.title()

def get_normalized_vendor(description: str) -> Optional[str]:
    """Return normalized vendor with UPI-specific handling; fallback to generic extraction."""
    upi_vendor = normalize_upi_vendor(description)
    if upi_vendor:
        return upi_vendor
    return extract_vendor(description)

def predict_next_transaction_date(
    last_date: datetime, recurrence_type: str, recurrence_interval: int
) -> datetime:
    """
    Calculates the next predicted transaction date based on recurrence.
    """
    if recurrence_type == "monthly":
        # Simple monthly addition, needs to handle month-end dates gracefully
        next_date = last_date + timedelta(days=30 * recurrence_interval) # Approximation
    elif recurrence_type == "weekly":
        next_date = last_date + timedelta(weeks=recurrence_interval)
    elif recurrence_type == "yearly":
        next_date = last_date + timedelta(days=365 * recurrence_interval) # Approximation
    else:
        raise ValueError(f"Unknown recurrence type: {recurrence_type}")
    
    return next_date

def calculate_confidence(transaction_count: int, consistency_score: float) -> float:
    """
    Generates a confidence score based on the number of transactions and consistency.
    `consistency_score` could be derived from date regularity, amount consistency, etc.
    """
    score = (transaction_count * 10 + consistency_score * 90) / 100 # Example formula
    return min(100.0, max(0.0, float(score)))

def predict_amount(amounts: List[Decimal]) -> Decimal:
    """
    Estimates the predicted amount based on the median of past amounts.
    """
    if not amounts:
        return Decimal('0.00')
    sorted_amounts = sorted(amounts)
    mid = len(sorted_amounts) // 2
    if len(sorted_amounts) % 2 == 0:
        return (sorted_amounts[mid - 1] + sorted_amounts[mid]) / 2
    else:
        return sorted_amounts[mid]

# --- Core Pattern Detection Logic ---

async def detect_patterns(
    user_id: UUID, transactions: List[Transaction], amount_tolerance_percent: float = 50.0
) -> List[Dict]:
    """
    Detects recurring spending patterns for a given user from a list of transactions.
    """
    logger.info(f"[detect_patterns] Starting pattern detection for user: {user_id} with {len(transactions)} transactions.")
    grouped_patterns = defaultdict(list)
    for transaction in transactions:
        raw_desc = transaction.description or ""
        vendor = get_normalized_vendor(raw_desc)
        logger.info(f"[detect_patterns] Transaction: id={transaction.id}, amount={transaction.amount}, type={transaction.type}, category_id={transaction.category_id}, vendor='{vendor}', raw_desc='{raw_desc[:60]}'")
        if vendor and 'upi' in raw_desc.lower():
            logger.debug(f"[detect_patterns] UPI normalization: '{raw_desc[:60]}' -> '{vendor}'")
        category_id = transaction.category_id
        tx_type = transaction.type  # 'expense' or 'income'
        # Group by vendor, category, and transaction type to avoid mixing income/expense patterns
        key = (vendor, category_id, tx_type)
        grouped_patterns[key].append(transaction)
    
    recurring_patterns = []

    for key, transactions_in_group in grouped_patterns.items():
        if len(transactions_in_group) < 2: # Need at least two transactions to detect a pattern
            logger.info(f"[detect_patterns] Skipping pattern for {key}: Less than 2 transactions in group.")
            continue
        
        transactions_in_group.sort(key=lambda t: t.date)

        dates = [t.date for t in transactions_in_group]
        amounts = [t.amount for t in transactions_in_group]

        median_amount = predict_amount(amounts)
        inconsistent = []
        consistent_amounts = True
        for amount in amounts:
            if median_amount != 0 and abs((amount - median_amount) / median_amount * 100) > amount_tolerance_percent:
                inconsistent.append(amount)
                consistent_amounts = False
        if not consistent_amounts:
            logger.info(f"[detect_patterns] Skipping pattern for {key}: Amounts too varied. Median: {median_amount}, Offenders: {inconsistent}")
            continue # Amounts too varied for a reliable pattern

        time_diffs = []
        for i in range(1, len(dates)):
            diff = dates[i] - dates[i-1]
            time_diffs.append(diff)
        
        if not time_diffs:
            logger.info(f"[detect_patterns] Skipping pattern for {key}: No time differences to analyze (single transaction after filtering?).")
            continue

        avg_diff_days = sum(td.days for td in time_diffs) / len(time_diffs)
        
        recurrence_type = None
        recurrence_interval = None
        
        if 5 <= avg_diff_days <= 9:
            recurrence_type = "weekly"
            recurrence_interval = 1
        elif 12 <= avg_diff_days <= 18:
            recurrence_type = "bi-weekly"
            recurrence_interval = 2
        elif 26 <= avg_diff_days <= 35:
            recurrence_type = "monthly"
            recurrence_interval = 1
        elif 80 <= avg_diff_days <= 100:
            recurrence_type = "quarterly"
            recurrence_interval = 3
        elif 330 <= avg_diff_days <= 400:
            recurrence_type = "yearly"
            recurrence_interval = 1

        if recurrence_type == "monthly":
            recurrence_interval = max(1, round(avg_diff_days / 30))
        elif recurrence_type == "weekly":
            recurrence_interval = max(1, round(avg_diff_days / 7))
        elif recurrence_type == "yearly":
            recurrence_interval = max(1, round(avg_diff_days / 365))

        if not recurrence_type:
            logger.info(f"[detect_patterns] Skipping pattern for {key}: Could not determine a clear recurrence pattern. Avg diff: {avg_diff_days:.2f} days.")
            continue 

        # Unpack key (vendor, category_id, transaction_type)
        if isinstance(key, tuple) and len(key) == 3:
            vendor, category_id, transaction_type = key
        else:
            # Legacy support (vendor, category_id) -> default expense
            vendor, category_id = key
            transaction_type = 'expense'
        pattern_name = f"{vendor or 'Unknown'} {transactions_in_group[0].description[:20]} (Recurring)" if vendor else f"{transactions_in_group[0].description[:30]} (Recurring)"

        consistency_score_val = 100.0 if consistent_amounts and all(td.days > 0 for td in time_diffs) else 50.0 
        confidence_score_val = calculate_confidence(len(transactions_in_group), consistency_score_val)

        next_prediction_date_val = predict_next_transaction_date(
            dates[-1], recurrence_type, recurrence_interval
        )
        predicted_amount_val = predict_amount(amounts)

        recurring_patterns.append({
            "user_id": user_id,
            "pattern_name": pattern_name,
            "category_id": category_id,
            "recurrence_type": recurrence_type,
            "recurrence_interval": recurrence_interval,
            "source_vendor": vendor,
            "next_prediction_date": next_prediction_date_val,
            "predicted_amount": predicted_amount_val,
            "confidence_score": Decimal(str(confidence_score_val)),
            "agent_notes": f"Detected {recurrence_type} pattern with {len(transactions_in_group)} transactions. Average interval: {avg_diff_days:.2f} days.",
            "transaction_type": transaction_type,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        })
        logger.info(f"[detect_patterns] Detected pattern: {pattern_name} for user {user_id}. Next prediction: {next_prediction_date_val.strftime('%Y-%m-%d')}")
    
    logger.info(f"[detect_patterns] Finished pattern detection for user: {user_id}. Found {len(recurring_patterns)} patterns.")
    return recurring_patterns

# --- Database Insert/Update Logic ---

async def upsert_spend_analysis(
    session: AsyncSession, pattern_data: Dict
) -> SpendAnalysis:
    """
    Inserts a new spend analysis record or updates an existing one.
    """
    logger.info(f"[upsert_spend_analysis] Attempting to upsert pattern: {pattern_data['pattern_name']} for user {pattern_data['user_id']}")
    # Attempt to find an existing pattern for the user and pattern name
    stmt = select(SpendAnalysis).filter_by(
        user_id=pattern_data["user_id"],
        pattern_name=pattern_data["pattern_name"],
        transaction_type=pattern_data["transaction_type"],
    )
    existing_pattern = (await session.execute(stmt)).scalar_one_or_none()

    if existing_pattern:
        logger.info(f"[upsert_spend_analysis] Updating existing pattern for {pattern_data['pattern_name']}")
        # Update existing pattern
        existing_pattern.next_prediction_date = pattern_data["next_prediction_date"]
        existing_pattern.predicted_amount = pattern_data["predicted_amount"]
        existing_pattern.confidence_score = pattern_data["confidence_score"]
        existing_pattern.agent_notes = pattern_data["agent_notes"]
        existing_pattern.updated_at = datetime.now()
        existing_pattern.recurrence_type = pattern_data["recurrence_type"]
        existing_pattern.recurrence_interval = pattern_data["recurrence_interval"]
        existing_pattern.source_vendor = pattern_data["source_vendor"]
        existing_pattern.category_id = pattern_data["category_id"]
        existing_pattern.transaction_type = pattern_data["transaction_type"]
        # Reset notification_sent if the prediction date is in the future and it was previously sent
        if existing_pattern.notification_sent and existing_pattern.next_prediction_date > datetime.now():
            existing_pattern.notification_sent = False
        return existing_pattern
    else:
        logger.info(f"[upsert_spend_analysis] Creating new pattern for {pattern_data['pattern_name']}")
        # Create new pattern
        new_pattern = SpendAnalysis(**pattern_data)
        session.add(new_pattern)
        return new_pattern

async def run_spend_analysis_agent():
    """
    Orchestrates the recurring spend analysis process for all users with unprocessed transactions.
    This function is designed to be called by a Celery task.
    """
    logger.info("Starting spend analysis agent run...")
    processed_transaction_ids = []

    # Create fresh engine for this event loop (asyncio.run creates new loop each time)
    engine = create_async_engine(DATABASE_URL, echo=False, poolclass=sqlalchemy.pool.NullPool)
    SessionFactory = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

    async with SessionFactory() as session:
        try:
            # Advisory lock to prevent overlapping runs (lock key chosen arbitrarily)
            result = await session.execute(text("SELECT pg_try_advisory_lock(938475)"))
            lock_result = result.scalar()
            if not lock_result:
                logger.info("Another spend analysis run is active. Skipping this execution.")
                return
            logger.info("Fetching all unprocessed transactions...")
            # Fetch all unprocessed transactions, group by user
            unprocessed_transactions = (
                await session.execute(
                    select(Transaction)
                    .filter(Transaction.processed == False)
                    .filter(Transaction.type.in_(['expense', 'income']))
                    .order_by(Transaction.user_id, Transaction.date)
                )
            ).scalars().all()
            logger.info(f"Fetched {len(unprocessed_transactions)} unprocessed transactions.")

            transactions_by_user: Dict[UUID, List[Transaction]] = defaultdict(list)
            for transaction in unprocessed_transactions:
                transactions_by_user[transaction.user_id].append(transaction)
                processed_transaction_ids.append(transaction.id)

            if not transactions_by_user:
                logger.info("No unprocessed transactions found for any user. Skipping analysis.")

            for user_id, transactions in transactions_by_user.items():
                logger.info(f"Analyzing {len(transactions)} unprocessed transactions for user: {user_id}")
                
                # Detect recurring patterns for the user
                detected_patterns = await detect_patterns(user_id, transactions)
                logger.info(f"Detected {len(detected_patterns)} patterns for user: {user_id}.")

                # Upsert results into spend_analysis table
                for pattern_data in detected_patterns:
                    await upsert_spend_analysis(session, pattern_data)
            
            # Mark all processed transactions as processed=True
            if processed_transaction_ids:
                logger.info(f"Attempting to mark {len(processed_transaction_ids)} transactions as processed...")
                await session.execute(
                    update(Transaction)
                    .where(Transaction.id.in_(processed_transaction_ids))
                    .values(processed=True)
                )
                logger.info(f"Marked {len(processed_transaction_ids)} transactions as processed.")
            else:
                logger.info("No transactions to mark as processed.")

            # Additionally, mark any remaining unprocessed transactions (types other than income/expense) as processed
            logger.info("Marking any other unprocessed transactions as processed...")
            result_other_types = await session.execute(
                update(Transaction)
                .where(Transaction.processed == False)
                .where(~Transaction.type.in_(['expense', 'income']))
                .values(processed=True)
            )
            logger.info(f"Marked {result_other_types.rowcount or 0} other-type transactions as processed.")

            await session.commit()
            # Release advisory lock
            await session.execute(text("SELECT pg_advisory_unlock(938475)"))
            logger.info("Spend analysis agent run completed successfully. Session committed and lock released.")

        except Exception as e:
            await session.rollback()
            logger.error(f"Error during spend analysis agent run: {e}", exc_info=True)
            raise # Re-raise for Celery to handle retries
        finally:
            await engine.dispose()

# --- Celery Task Definition ---

@celery_app.task(bind=True, default_retry_delay=300, max_retries=5)
def process_transactions_for_spend_analysis(self):
    """
    Celery task to trigger the recurring spend analysis agent.
    This task does not pass transactions; the agent loads them directly from the DB.
    """
    logger.info("Celery task 'process_transactions_for_spend_analysis' started.")
    try:
        import asyncio
        asyncio.run(run_spend_analysis_agent())
        logger.info("Celery task 'process_transactions_for_spend_analysis' completed successfully.")
    except Exception as exc:
        logger.error(f"Celery task 'process_transactions_for_spend_analysis' failed: {exc}", exc_info=True)
        raise self.retry(exc=exc)

# --- Celery Beat Schedule Example ---

# To integrate this with your Celery Beat, you'll typically add this to your
# Celery app configuration (e.g., in app/celery_app.py or a separate config file).
# Ensure the 'task' name matches the decorated Celery task function.

# Note: Beat schedule is configured centrally in app/celery_app.py.
