from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_current_user
from app.models.user import User
from app.models.currency import Currency
from app.schemas.user import UserResponse, UserUpdate
from app.logging_config import get_logger
from sqlalchemy import select

logger = get_logger(__name__)
router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current authenticated user's profile"""
    try:
        # Refresh user to get latest data
        await db.refresh(current_user)
        return current_user
    except Exception as e:
        logger.error(f"Error fetching user profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch user profile"
        )


@router.put("/me", response_model=UserResponse)
async def update_current_user_profile(
    user_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update current authenticated user's profile"""
    try:
        # Validate currency_id if provided
        if user_data.currency_id is not None:
            result = await db.execute(
                select(Currency).where(Currency.id == user_data.currency_id)
            )
            currency = result.scalar_one_or_none()
            if not currency:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Currency not found"
                )

        # Update fields
        update_data = user_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(current_user, field, value)

        await db.commit()
        await db.refresh(current_user)

        logger.info(f"Updated user profile for user {current_user.id}")
        return current_user

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user profile: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user profile"
        )

