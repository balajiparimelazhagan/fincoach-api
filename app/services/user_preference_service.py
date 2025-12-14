from typing import Optional
from datetime import datetime
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user_preference import UserPreference
from app.logging_config import get_logger

logger = get_logger(__name__)

# Default preferences for new users
DEFAULT_PREFERENCES = {
    "dashboard": {
        "show_ai_suggestions": True,
        "show_budget_summary": True,
        "show_income_expense": True,
        "show_transaction_list": True,
        "show_category_breakdown": True
    }
}


async def get_user_preferences(db: AsyncSession, user_id: str) -> Optional[UserPreference]:
    """
    Get user preferences from database.
    """
    # Query for existing preferences
    result = await db.execute(
        select(UserPreference).where(UserPreference.user_id == user_id)
    )
    preferences = result.scalar_one_or_none()
    
    if preferences:
        logger.info(f"Retrieved preferences for user {user_id}")
        return preferences
    
    # Create default preferences if none exist
    logger.info(f"Creating default preferences for user {user_id}")
    new_preferences = UserPreference(
        id=str(uuid.uuid4()),
        user_id=user_id,
        ui_preferences=DEFAULT_PREFERENCES.copy()
    )
    db.add(new_preferences)
    await db.commit()
    await db.refresh(new_preferences)
    
    logger.info(f"Created default preferences for user {user_id}")
    return new_preferences


async def update_user_preferences(
    db: AsyncSession, 
    user_id: str, 
    preferences_data: dict
) -> UserPreference:
    """
    Update user preferences in database.
    Supports deep merge of nested preferences.
    """
    # Deep merge function
    def deep_merge(base: dict, update: dict) -> dict:
        """Recursively merge update dict into base dict"""
        result = base.copy()
        for key, value in update.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    
    # Get existing preferences or create new
    result = await db.execute(
        select(UserPreference).where(UserPreference.user_id == user_id)
    )
    preferences = result.scalar_one_or_none()
    
    if not preferences:
        # Create new preferences if none exist
        logger.info(f"Creating new preferences for user {user_id}")
        preferences = UserPreference(
            id=str(uuid.uuid4()),
            user_id=user_id,
            ui_preferences=deep_merge(DEFAULT_PREFERENCES.copy(), preferences_data)
        )
        db.add(preferences)
    else:
        # Update existing preferences
        logger.info(f"Updating preferences for user {user_id}")
        preferences.ui_preferences = deep_merge(preferences.ui_preferences, preferences_data)
    
    await db.commit()
    await db.refresh(preferences)
    
    logger.info(f"Saved preferences for user {user_id}: {preferences_data}")
    return preferences
