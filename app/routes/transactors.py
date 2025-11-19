from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from app.dependencies import get_db, get_current_user
from app.models.user import User
from app.models.transactor import Transactor
from app.schemas.transactor import TransactorCreate, TransactorUpdate, TransactorResponse
from app.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/transactors", tags=["transactors"])


@router.post("", response_model=TransactorResponse, status_code=status.HTTP_201_CREATED)
async def create_transactor(
    transactor_data: TransactorCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new transactor for the current user"""
    try:
        new_transactor = Transactor(
            id=str(uuid.uuid4()),
            name=transactor_data.name,
            user_id=current_user.id,
            external_id=transactor_data.external_id,
            picture=transactor_data.picture
        )
        
        db.add(new_transactor)
        await db.commit()
        await db.refresh(new_transactor)
        
        logger.info(f"Created transactor {new_transactor.id} for user {current_user.id}")
        return new_transactor
        
    except Exception as e:
        logger.error(f"Error creating transactor: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create transactor"
        )


@router.get("", response_model=List[TransactorResponse])
async def get_transactors(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all transactors for the current user"""
    try:
        result = await db.execute(
            select(Transactor).where(Transactor.user_id == current_user.id)
        )
        transactors = result.scalars().all()
        return transactors
        
    except Exception as e:
        logger.error(f"Error fetching transactors: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch transactors"
        )


@router.get("/{transactor_id}", response_model=TransactorResponse)
async def get_transactor(
    transactor_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific transactor by ID"""
    try:
        result = await db.execute(
            select(Transactor).where(
                Transactor.id == transactor_id,
                Transactor.user_id == current_user.id
            )
        )
        transactor = result.scalar_one_or_none()
        
        if not transactor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transactor not found"
            )
        
        return transactor
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching transactor: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch transactor"
        )


@router.put("/{transactor_id}", response_model=TransactorResponse)
async def update_transactor(
    transactor_id: str,
    transactor_data: TransactorUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a transactor"""
    try:
        result = await db.execute(
            select(Transactor).where(
                Transactor.id == transactor_id,
                Transactor.user_id == current_user.id
            )
        )
        transactor = result.scalar_one_or_none()
        
        if not transactor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transactor not found"
            )
        
        # Update fields
        update_data = transactor_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(transactor, field, value)
        
        await db.commit()
        await db.refresh(transactor)
        
        logger.info(f"Updated transactor {transactor_id} for user {current_user.id}")
        return transactor
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating transactor: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update transactor"
        )


@router.delete("/{transactor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transactor(
    transactor_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a transactor"""
    try:
        result = await db.execute(
            select(Transactor).where(
                Transactor.id == transactor_id,
                Transactor.user_id == current_user.id
            )
        )
        transactor = result.scalar_one_or_none()
        
        if not transactor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transactor not found"
            )
        
        await db.delete(transactor)
        await db.commit()
        
        logger.info(f"Deleted transactor {transactor_id} for user {current_user.id}")
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting transactor: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete transactor"
        )

