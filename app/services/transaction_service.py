"""
Transaction service layer for business logic.
"""
from calendar import monthrange
from datetime import datetime
from typing import List, Tuple, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from sqlalchemy import and_
from fastapi import HTTPException

from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.transaction_schemas import UpdateScope
from app.logging_config import get_logger

logger = get_logger(__name__)


class TransactionQueryBuilder:
    """Builder class for constructing transaction queries."""
    
    def __init__(self, session: AsyncSession, user_id: str):
        self.session = session
        self.user_id = user_id
        self.conditions = [Transaction.user_id == user_id]
        self.eager_load = True
    
    def with_date_range(
        self,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None
    ) -> 'TransactionQueryBuilder':
        """Add date range filter."""
        if date_from:
            self.conditions.append(Transaction.date >= date_from)
        if date_to:
            self.conditions.append(Transaction.date <= date_to)
        return self
    
    def with_description_contains(self, description: Optional[str] = None) -> 'TransactionQueryBuilder':
        """Add description substring filter."""
        if description:
            like_expr = f"%{description}%"
            self.conditions.append(Transaction.description.ilike(like_expr))
        return self
    
    def with_amount_range(
        self,
        amount_min: Optional[float] = None,
        amount_max: Optional[float] = None
    ) -> 'TransactionQueryBuilder':
        """Add amount range filter."""
        if amount_min is not None:
            self.conditions.append(Transaction.amount >= amount_min)
        if amount_max is not None:
            self.conditions.append(Transaction.amount <= amount_max)
        return self
    
    def with_type(self, transaction_type: Optional[str] = None) -> 'TransactionQueryBuilder':
        """Add transaction type filter."""
        if transaction_type:
            self.conditions.append(Transaction.type == transaction_type)
        return self
    
    def with_transactor(self, transactor_id: Optional[str] = None) -> 'TransactionQueryBuilder':
        """Add transactor filter."""
        if transactor_id:
            self.conditions.append(Transaction.transactor_id == transactor_id)
        return self
    
    def with_category(self, category_id: Optional[str] = None) -> 'TransactionQueryBuilder':
        """Add category filter."""
        if category_id:
            self.conditions.append(Transaction.category_id == category_id)
        return self
    
    async def count(self) -> int:
        """Get count of transactions matching filters."""
        stmt = select(Transaction).filter(and_(*self.conditions))
        result = await self.session.execute(stmt)
        return len(result.scalars().all())
    
    async def fetch(
        self,
        limit: int = 50,
        offset: int = 0,
        order_by_date_desc: bool = True
    ) -> List[Transaction]:
        """Fetch transactions with pagination."""
        stmt = select(Transaction).filter(and_(*self.conditions))
        
        if self.eager_load:
            stmt = stmt.options(
                joinedload(Transaction.transactor),
                joinedload(Transaction.category),
                joinedload(Transaction.account)
            )
        
        if order_by_date_desc:
            stmt = stmt.order_by(Transaction.date.desc())
        
        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()


class TransactionUpdateService:
    """Service for handling transaction update operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_transaction_by_id(
        self,
        transaction_id: str,
        user_id: str
    ) -> Transaction:
        """
        Fetch a transaction by ID with loaded relationships.
        
        Args:
            transaction_id: Transaction UUID
            user_id: User UUID for authorization
            
        Returns:
            Transaction instance
            
        Raises:
            HTTPException: If transaction not found
        """
        transaction = (
            await self.session.execute(
                select(Transaction)
                .filter(and_(
                    Transaction.id == transaction_id,
                    Transaction.user_id == user_id
                ))
                .options(
                    joinedload(Transaction.transactor),
                    joinedload(Transaction.category),
                    joinedload(Transaction.account)
                )
            )
        ).scalar_one_or_none()
        
        if not transaction:
            raise HTTPException(status_code=404, detail="Transaction not found")
        
        return transaction
    
    async def update_single_transaction(
        self,
        transaction: Transaction,
        category_id: Optional[str] = None,
        transactor_label: Optional[str] = None
    ) -> Transaction:
        """
        Update a single transaction.
        
        Args:
            transaction: Transaction to update
            category_id: New category ID (optional)
            transactor_label: New transactor label (optional)
            
        Returns:
            Updated transaction
        """
        if category_id is not None:
            transaction.category_id = category_id
        
        if transactor_label is not None and transaction.transactor:
            transaction.transactor.label = transactor_label
        
        await self.session.commit()
        await self.session.refresh(transaction, ['transactor', 'category', 'account'])
        
        return transaction
    
    def _calculate_month_boundaries(self, date: datetime) -> Tuple[datetime, datetime]:
        """
        Calculate start and end of month for a given date.
        
        Args:
            date: Reference date
            
        Returns:
            Tuple of (month_start, month_end)
        """
        month_start = date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_day = monthrange(date.year, date.month)[1]
        month_end = date.replace(
            day=last_day,
            hour=23, minute=59, second=59, microsecond=999999
        )
        return month_start, month_end
    
    async def _get_transactions_for_scope(
        self,
        transaction: Transaction,
        scope: UpdateScope
    ) -> List[Transaction]:
        """
        Get transactions to update based on scope.
        
        Args:
            transaction: Original transaction
            scope: Update scope enum
            
        Returns:
            List of transactions to update
        """
        if not transaction.transactor_id:
            raise HTTPException(status_code=400, detail="Transaction has no transactor")
        
        tx_date = transaction.date
        month_start, month_end = self._calculate_month_boundaries(tx_date)
        
        # Build query based on scope
        base_conditions = [
            Transaction.user_id == transaction.user_id,
            Transaction.transactor_id == transaction.transactor_id
        ]
        
        if scope == UpdateScope.CURRENT_AND_FUTURE:
            base_conditions.append(Transaction.date >= tx_date)
        elif scope == UpdateScope.MONTH_ONLY:
            base_conditions.extend([
                Transaction.date >= month_start,
                Transaction.date <= month_end
            ])
        elif scope == UpdateScope.MONTH_AND_FUTURE:
            base_conditions.append(Transaction.date >= month_start)
        
        result = await self.session.execute(
            select(Transaction)
            .filter(and_(*base_conditions))
            .options(joinedload(Transaction.transactor))
        )
        
        return result.scalars().all()
    
    async def bulk_update_transactions(
        self,
        transaction_id: str,
        user_id: str,
        scope: UpdateScope,
        category_id: Optional[str] = None,
        transactor_label: Optional[str] = None
    ) -> Tuple[int, Transaction]:
        """
        Update multiple transactions based on scope.
        
        Args:
            transaction_id: ID of the reference transaction
            user_id: User ID for authorization
            scope: Update scope (single, current_and_future, month_only, month_and_future)
            category_id: New category ID (optional)
            transactor_label: New transactor label (optional)
            
        Returns:
            Tuple of (updated_count, updated_transaction)
            
        Raises:
            HTTPException: If transaction not found or invalid scope
        """
        # Get original transaction
        original_tx = await self.get_transaction_by_id(transaction_id, user_id)
        
        # Handle single transaction update
        if scope == UpdateScope.SINGLE:
            await self.update_single_transaction(
                original_tx,
                category_id=category_id,
                transactor_label=transactor_label
            )
            return 1, original_tx
        
        # Get transactions to update based on scope
        transactions_to_update = await self._get_transactions_for_scope(original_tx, scope)
        
        # Update category for all matching transactions
        updated_count = 0
        if category_id is not None:
            for tx in transactions_to_update:
                tx.category_id = category_id
                updated_count += 1
        
        # Update transactor label (affects all transactions with this transactor)
        if transactor_label is not None and original_tx.transactor:
            original_tx.transactor.label = transactor_label
        
        await self.session.commit()
        await self.session.refresh(original_tx, ['transactor', 'category', 'account'])
        
        logger.info(
            f"Bulk updated {updated_count} transactions for user {user_id} "
            f"with scope {scope.value}"
        )
        
        return updated_count, original_tx
