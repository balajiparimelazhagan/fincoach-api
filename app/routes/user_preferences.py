from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_current_user
from app.models.user import User
from app.schemas.user_preference import UserPreferenceResponse, UserPreferenceUpdate
from app.services.user_preference_service import get_user_preferences, update_user_preferences
from app.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/user-preferences", tags=["user-preferences"])


@router.get("", response_model=UserPreferenceResponse)
async def get_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current user's dashboard preferences.
    Returns mock data for now.
    """
    try:
        preferences = await get_user_preferences(db, current_user.id)
        if not preferences:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User preferences not found"
            )
        return preferences
    except Exception as e:
        logger.error(f"Error fetching user preferences: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch user preferences"
        )


@router.put("", response_model=UserPreferenceResponse)
async def update_preferences(
    preferences_data: UserPreferenceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update current user's dashboard preferences.
    Updates mock data for now.
    Supports partial updates and nested preference structure.
    """
    try:
        if not preferences_data.ui_preferences:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No preferences provided for update"
            )
        
        updated_preferences = await update_user_preferences(
            db, 
            current_user.id, 
            preferences_data.ui_preferences
        )
        
        logger.info(f"Updated preferences for user {current_user.id}")
        return updated_preferences
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user preferences: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user preferences"
        )
