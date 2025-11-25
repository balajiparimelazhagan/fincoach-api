"""
Integrated Email Parser + Gmail Fetcher
Fetches bank emails from Gmail and parses them into transactions.
"""

from .gmail_fetcher import GmailFetcher
from agent import EmailParserAgent
from agent.email_parser import Transaction as ParsedTransaction
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from typing import Dict, List, Optional
import asyncio
from app.db import AsyncSessionLocal
from app.models.transaction import Transaction as DBTransaction
from app.models.category import Category
from app.models.transactor import Transactor
from app.models.currency import Currency
from app.models.user import User
from sqlalchemy.future import select
from sqlalchemy.exc import NoResultFound
from app.logging_config import get_logger
from app.config import settings

logger = get_logger(__name__)


async def fetch_and_parse_all_users_emails(max_emails: Optional[int] = None):
    """
    Fetches emails for all active users and parses them into transactions.
    """
    logger.info("Starting email fetching and parsing for all users...")
    async with AsyncSessionLocal() as session:
        users = (await session.execute(select(User))).scalars().all()
        if not users:
            logger.info("No users found in the database.")
            return
        
        for user in users:
            logger.info(f"Processing emails for user: {user.id}. Current last_email_fetch_time: {user.last_email_fetch_time}")
            await fetch_and_parse_bank_emails_for_user(max_emails=max_emails, user_id=str(user.id))


async def fetch_and_parse_bank_emails_for_user(max_emails: Optional[int] = None, user_id: Optional[str] = None):
    """
    Fetch bank emails from Gmail for a specific user and parse them into transactions.
    
    Args:
        max_emails: Maximum number of emails to fetch
        user_id: The ID of the user for whom to fetch and save transactions.
    """
    if not user_id:
        logger.warning("User ID is required for fetching and saving transactions.")
        return

    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).filter_by(id=user_id))).scalar_one_or_none()
        if not user:
            logger.warning(f"User with ID {user_id} not found.")
            return

        # Initialize fetcher and parser
        try:
            fetcher = GmailFetcher(
                credentials_data=user.google_credentials_json,
                token_data=user.google_token_pickle
            )
        except Exception as e:
            logger.error(f"Error initializing GmailFetcher for user {user.id}: {e}")
            return
        
        parser = EmailParserAgent()
        
        # Calculate since_date based on last_email_fetch_time, with a configured maximum lookback
        since_date = datetime.now(timezone.utc) - timedelta(days=settings.EMAIL_FETCH_DAYS)
        
        if user.last_email_fetch_time and user.last_email_fetch_time > since_date:
            since_date = user.last_email_fetch_time
            logger.info(f"Using last email fetch time for user {user.id}: {user.last_email_fetch_time.strftime('%Y/%m/%d %H:%M:%S')}")
        else:
            logger.info(f"No last email fetch time or it's older than {settings.EMAIL_FETCH_DAYS} days. Fetching from {since_date.strftime('%Y/%m/%d %H:%M:%S')} for user {user.id}.")
        
        # Default to 10 emails if not specified (fetch 10 older mails since since_date)
        if max_emails is None:
            max_emails = 10

        # Fetch emails
        logger.info(f"Fetching up to {max_emails} bank emails for user {user.id} since {since_date.strftime('%Y/%m/%d')}")
        # Request ascending order so we fetch older emails first (uses query chunking under the hood)
        emails = fetcher.fetch_bank_emails(max_results=max_emails, since_date=since_date, ascending=True)
        
        if not emails:
            logger.info(f"No bank emails found for user {user.id}")
            return

        logger.info(f"Found {len(emails)} emails for user {user.id}. Parsing...")
        # Parse emails
        transactions = []

        # Compute latest email date (if present) in a single line
        latest_email_date = None
        try:
            # Extract any date values from 4-tuples returned by GmailFetcher
            email_dates = [e[3] for e in emails if len(e) >= 4 and isinstance(e[3], datetime)]
            latest_email_date = max(email_dates) if email_dates else None
        except Exception:
            latest_email_date = None

        logger.debug(f"Latest email date for user {user.id}: {latest_email_date}")
        # Parse each email (ignore the date for parsing; it's used only to set last_email_fetch_time)
        for i, email_item in enumerate(emails, 1):
            try:
                message_id, subject, body = email_item[:3]
            except Exception:
                logger.warning(f"Unexpected email format for user {user.id}: {email_item}")
                continue

            transaction = parser.parse_email(message_id, subject, body)
            if transaction:
                transactions.append(transaction)
            else:
                logger.warning(f"     ✗ Failed to parse email for user {user.id}: {subject[:50]}...")
        
        if transactions:
            logger.info(f"Parsed {len(transactions)} transactions for user {user.id}. Saving to DB...")
            await save_transactions_to_db(transactions, user_id)
        else:
            logger.info(f"No transactions parsed for user {user.id}.")

        # Update last_email_fetch_time after processing using latest email date if available
        if latest_email_date:
            user.last_email_fetch_time = latest_email_date
        else:
            user.last_email_fetch_time = datetime.now(timezone.utc)
        
        logger.debug(f"Updated last_email_fetch_time to: {user.last_email_fetch_time} for user: {user.id}")
        session.add(user)
        await session.commit()
        logger.info(f"Updated last_email_fetch_time for user {user.id} to {user.last_email_fetch_time.strftime('%Y/%m/%d %H:%M:%S')}")
    
    
async def save_transactions_to_db(parsed_transactions: List[ParsedTransaction], user_id: str):
    async with AsyncSessionLocal() as session:
        for parsed_transaction in parsed_transactions:
            try:
                # Get or create Category
                category_obj = (await session.execute(select(Category).filter_by(label=parsed_transaction.category))).scalar_one_or_none()
                if not category_obj:
                    try:
                        category_obj = Category(label=parsed_transaction.category)
                        session.add(category_obj)
                        await session.flush()
                        logger.info(f"Created new category '{category_obj.label}'.")
                    except Exception as e:
                        logger.error(f"Error creating/flushing category '{parsed_transaction.category}': {e}", exc_info=True)
                        raise # Re-raise to abort transaction and see full traceback
                
                # Get or create Transactor
                transactor_obj = (await session.execute(select(Transactor).filter_by(name=parsed_transaction.source, user_id=user_id))).scalar_one_or_none()
                if not transactor_obj:
                    try:
                        transactor_obj = Transactor(name=parsed_transaction.source, user_id=user_id)
                        session.add(transactor_obj)
                        await session.flush()
                        logger.info(f"Created new transactor '{transactor_obj.name}' for user {user_id}.")
                    except Exception as e:
                        logger.error(f"Error creating/flushing transactor '{parsed_transaction.source}' for user {user_id}: {e}", exc_info=True)
                        raise

                # Get Currency (assuming a default INR for now or fetching from user settings)
                currency_obj = (await session.execute(select(Currency).filter_by(value="INR"))).scalar_one_or_none()
                if not currency_obj:
                    logger.warning("INR currency not found. Please ensure currencies are populated.")
                    # Create a default INR if not found to prevent errors
                    try:
                        currency_obj = Currency(name="Indian Rupee", value="INR", country="India") # Added country
                        session.add(currency_obj)
                        await session.flush()
                        logger.info(f"Created default INR currency.")
                    except Exception as e:
                        logger.error(f"Error creating/flushing currency 'INR': {e}", exc_info=True)
                        raise

                # Create DBTransaction object
                try:
                    db_transaction = DBTransaction(
                        amount=parsed_transaction.amount,
                        type=parsed_transaction.transaction_type.value,
                        date=datetime.strptime(parsed_transaction.date, "%Y-%m-%d %H:%M:%S"),
                        description=parsed_transaction.description,
                        confidence=str(parsed_transaction.confidence),
                        user_id=user_id,
                        category_id=category_obj.id if category_obj else None,
                        transactor_id=transactor_obj.id if transactor_obj else None,
                        currency_id=currency_obj.id if currency_obj else None,
                        message_id=parsed_transaction.message_id
                    )
                    session.add(db_transaction)
                except Exception as e:
                    logger.error(f"Error creating/adding DBTransaction for user {user_id}: {e}", exc_info=True)
                    raise

            except Exception as e:
                logger.error(f"Unhandled exception during transaction saving for user {user_id}: {e}", exc_info=True)
                await session.rollback() # Rollback the transaction on any error
                raise # Re-raise the exception to propagate it further
        await session.commit()
