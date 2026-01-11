"""
Transaction routes for the FinCoach API.

This module provides endpoints for:
- Listing transactions with filtering and pagination
- Getting a single transaction by ID
- Updating a single transaction
- Bulk updating transactions with different scopes
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.models.user import User
from app.dependencies import get_current_user
from app.schemas.transaction_schemas import (
    TransactionUpdateRequest,
    BulkTransactionUpdateRequest,
    TransactionResponse,
    BulkUpdateResponse,
    TransactionListResponse,
)
from app.services.transaction_service import (
    TransactionQueryBuilder,
    TransactionUpdateService,
)
from app.utils.transaction_serializer import serialize_transaction
from app.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/transactions", tags=["Transactions"])


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction_by_id(
    transaction_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """
    Get a single transaction by ID.
    
    Args:
        transaction_id: UUID of the transaction
        current_user: Authenticated user from JWT token
        session: Database session
        
    Returns:
        Serialized transaction with all relationships
        
    Raises:
        HTTPException: 404 if transaction not found
    """
    service = TransactionUpdateService(session)
    transaction = await service.get_transaction_by_id(transaction_id, current_user.id)
    return serialize_transaction(transaction)


@router.patch("/{transaction_id}/bulk", response_model=BulkUpdateResponse)
async def bulk_update_transactions(
    transaction_id: str,
    update_data: BulkTransactionUpdateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """
    Bulk update transactions based on scope.
    
    Supports four update scopes:
    - **single**: Update only the specified transaction
    - **current_and_future**: Update current transaction and all future from same transactor
    - **month_only**: Update all transactions from same transactor in current month only
    - **month_and_future**: Update all transactions from same transactor in current month and future
    
    Args:
        transaction_id: UUID of the reference transaction
        update_data: Update payload with category_id, transactor_label, and scope
        current_user: Authenticated user from JWT token
        session: Database session
        
    Returns:
        Dictionary with updated_count and serialized transaction
        
    Raises:
        HTTPException: 400 if invalid scope, 404 if transaction not found
    """
    service = TransactionUpdateService(session)
    
    updated_count, transaction = await service.bulk_update_transactions(
        transaction_id=transaction_id,
        user_id=current_user.id,
        scope=update_data.update_scope,
        category_id=update_data.category_id,
        transactor_label=update_data.transactor_label,
    )
    
    return {
        "updated_count": updated_count,
        "transaction": serialize_transaction(transaction),
    }


@router.patch("/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(
    transaction_id: str,
    update_data: TransactionUpdateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """
    Update a single transaction's category and/or transactor label.
    
    Args:
        transaction_id: UUID of the transaction to update
        update_data: Update payload with optional category_id and transactor_label
        current_user: Authenticated user from JWT token
        session: Database session
        
    Returns:
        Serialized updated transaction
        
    Raises:
        HTTPException: 404 if transaction not found
    """
    service = TransactionUpdateService(session)
    transaction = await service.get_transaction_by_id(transaction_id, current_user.id)
    
    updated_transaction = await service.update_single_transaction(
        transaction=transaction,
        category_id=update_data.category_id,
        transactor_label=update_data.transactor_label,
    )
    
    return serialize_transaction(updated_transaction)


@router.get("", response_model=TransactionListResponse)
async def list_transactions(
    current_user: User = Depends(get_current_user),
    # Filters
    date_from: Optional[datetime] = Query(None, description="Start date (ISO8601)"),
    date_to: Optional[datetime] = Query(None, description="End date (ISO8601)"),
    description_contains: Optional[str] = Query(None, description="Substring match in description"),
    amount_min: Optional[float] = Query(None, description="Minimum amount"),
    amount_max: Optional[float] = Query(None, description="Maximum amount"),
    type: Optional[str] = Query(None, description="Transaction type (income/expense/saving)"),
    transactor_id: Optional[str] = Query(None, description="Filter by transactor ID"),
    category_id: Optional[str] = Query(None, description="Filter by category ID"),
    # Pagination
    limit: int = Query(50, ge=1, le=200, description="Max items to return"),
    offset: int = Query(0, ge=0, description="Items to skip"),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """
    List transactions for the authenticated user with filtering and pagination.
    
    The user_id is automatically extracted from the JWT token in the Authorization header.
    
    **Supported filters:**
    - Date range (date_from, date_to)
    - Description substring search
    - Amount range (amount_min, amount_max)
    - Transaction type
    - Transactor ID
    - Category ID
    
    **Pagination:**
    - Use `limit` and `offset` for pagination
    - Maximum limit is 200 items per request
    
    Args:
        current_user: Authenticated user from JWT token
        date_from: Start date for filtering
        date_to: End date for filtering
        description_contains: Substring to search in description
        amount_min: Minimum transaction amount
        amount_max: Maximum transaction amount
        type: Transaction type filter
        transactor_id: Filter by transactor
        category_id: Filter by category
        limit: Maximum items to return
        offset: Items to skip for pagination
        session: Database session
        
    Returns:
        Dictionary with count and list of transactions
    """
    # Build query with filters
    query_builder = (
        TransactionQueryBuilder(session, current_user.id)
        .with_date_range(date_from, date_to)
        .with_description_contains(description_contains)
        .with_amount_range(amount_min, amount_max)
        .with_type(type)
        .with_transactor(transactor_id)
        .with_category(category_id)
    )
    
    # Get count and transactions
    total_count = await query_builder.count()
    transactions = await query_builder.fetch(limit=limit, offset=offset)
    
    return {
        "count": total_count,
        "items": [serialize_transaction(t) for t in transactions],
    }
