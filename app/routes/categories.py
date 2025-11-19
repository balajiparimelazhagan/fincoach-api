from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from app.dependencies import get_db, get_current_user
from app.models.user import User
from app.models.category import Category
from app.schemas.category import CategoryCreate, CategoryUpdate, CategoryResponse
from app.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/categories", tags=["categories"])


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    category_data: CategoryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new category"""
    try:
        new_category = Category(
            id=str(uuid.uuid4()),
            label=category_data.label,
            picture=category_data.picture
        )
        
        db.add(new_category)
        await db.commit()
        await db.refresh(new_category)
        
        logger.info(f"Created category {new_category.id}")
        return new_category
        
    except Exception as e:
        logger.error(f"Error creating category: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create category"
        )


@router.get("", response_model=List[CategoryResponse])
async def get_categories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all categories"""
    try:
        result = await db.execute(select(Category))
        categories = result.scalars().all()
        return categories
        
    except Exception as e:
        logger.error(f"Error fetching categories: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch categories"
        )


@router.get("/{category_id}", response_model=CategoryResponse)
async def get_category(
    category_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific category by ID"""
    try:
        result = await db.execute(
            select(Category).where(Category.id == category_id)
        )
        category = result.scalar_one_or_none()
        
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found"
            )
        
        return category
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching category: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch category"
        )


@router.put("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: str,
    category_data: CategoryUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a category"""
    try:
        result = await db.execute(
            select(Category).where(Category.id == category_id)
        )
        category = result.scalar_one_or_none()
        
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found"
            )
        
        # Update fields
        update_data = category_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(category, field, value)
        
        await db.commit()
        await db.refresh(category)
        
        logger.info(f"Updated category {category_id}")
        return category
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating category: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update category"
        )


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a category"""
    try:
        result = await db.execute(
            select(Category).where(Category.id == category_id)
        )
        category = result.scalar_one_or_none()
        
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found"
            )
        
        await db.delete(category)
        await db.commit()
        
        logger.info(f"Deleted category {category_id}")
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting category: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete category"
        )

