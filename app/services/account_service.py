"""
Account Service
Handles account creation and retrieval operations.
"""
from typing import Optional
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account


async def get_or_create_account(
    session: AsyncSession,
    user_id: str,
    account_last_four: str,
    bank_name: str
) -> Account:
    """
    Get or create an account based on user_id and account_last_four.
    
    Args:
        session: SQLAlchemy async session
        user_id: UUID string of the user
        account_last_four: Last 4 digits of the account number
        bank_name: Name of the bank
        
    Returns:
        Account: The existing or newly created account
    """
    # Try to find existing account
    existing_account = (await session.execute(
        select(Account).filter_by(
            user_id=user_id,
            account_last_four=account_last_four
        )
    )).scalar_one_or_none()
    
    if existing_account:
        # Update bank name if it was not set or if new one is more specific
        if not existing_account.bank_name or existing_account.bank_name == "Unknown":
            existing_account.bank_name = bank_name
            await session.flush()
        return existing_account
    
    # Create new account
    new_account = Account(
        user_id=user_id,
        account_last_four=account_last_four,
        bank_name=bank_name
    )
    session.add(new_account)
    await session.flush()
    
    return new_account
