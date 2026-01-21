"""
Pattern Service

Orchestrates pattern discovery, obligation tracking, and LLM explanations.
Acts as the main interface for pattern-related operations.
"""
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Tuple
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc, func
import uuid

from app.logging_config import get_logger

logger = get_logger(__name__)

from agent.regex_constants import CURRENCY_SYMBOLS
from app.models import (
    Transaction, RecurringPattern, RecurringPatternStreak,
    PatternTransaction, PatternObligation, Transactor,
    User, Currency
)
from agent.pattern_discovery_engine import (
    DeterministicPatternDiscovery,
    Transaction as DiscoveryTransaction,
    PatternCandidate,
    PatternCase,
    AmountBehaviorType
)
from agent.pattern_obligation_manager import (
    PatternObligationManager,
    PatternState,
    TransactionProcessor
)
from agent.pattern_explanation_agent import PatternExplanationAgent


class PatternService:
    """
    Service layer for recurring pattern analysis.
    
    Responsibilities:
    - Discover patterns from transaction history
    - Track pattern state and obligations
    - Generate user-friendly explanations
    - Handle incremental updates on new transactions
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.explanation_agent = PatternExplanationAgent()
    
    @staticmethod
    def _get_currency_symbol(currency_code: str) -> str:
        """Convert currency code to symbol"""
        return CURRENCY_SYMBOLS.get(currency_code, currency_code)
    
    # ===== PATTERN DISCOVERY =====
    
    async def discover_patterns_for_user(
        self,
        user_id: uuid.UUID,
        transactor_id: Optional[uuid.UUID] = None,
        direction: Optional[str] = None
    ) -> List[Dict]:
        """
        Run pattern discovery on user's transaction history.
        
        Args:
            user_id: User to analyze
            transactor_id: Optional - analyze only this transactor
            direction: Optional - 'DEBIT' or 'CREDIT'
        
        Returns:
            List of discovered patterns with explanations
        """
        logger.info(f"[PATTERN_DISCOVERY] Starting pattern discovery for user {user_id}, "
                   f"transactor_id={transactor_id}, direction={direction}")
        
        # Get unique transactor-direction-currency combinations
        groups = await self._get_transaction_groups(user_id, transactor_id, direction)
        logger.info(f"[PATTERN_DISCOVERY] Found {len(groups)} transaction groups to analyze")
        
        discovered_patterns = []
        
        for group in groups:
            # Run discovery for this group
            patterns = await self._discover_patterns_for_group(
                user_id=user_id,
                transactor_id=group['transactor_id'],
                direction=group['direction'],
                currency_id=group['currency_id']
            )
            discovered_patterns.extend(patterns)
        
        return discovered_patterns
    
    async def _get_transaction_groups(
        self,
        user_id: uuid.UUID,
        transactor_id: Optional[uuid.UUID],
        direction: Optional[str]
    ) -> List[Dict]:
        """Get unique (transactor, direction, currency) groups for analysis"""
        logger.debug(f"[PATTERN_DISCOVERY] Grouping transactions for user {user_id}")
        logger.debug(f"[PATTERN_DISCOVERY] Filters: transactor_id={transactor_id}, direction={direction}")
        
        stmt = select(
            Transaction.transactor_id,
            Transaction.type.label('direction'),
            Transaction.currency_id,
            func.count(Transaction.id).label('count')
        ).where(
            Transaction.user_id == user_id,
            Transaction.transactor_id.isnot(None)
        )
        
        if transactor_id:
            logger.debug(f"[PATTERN_DISCOVERY] Filtering by transactor_id: {transactor_id}")
            stmt = stmt.where(Transaction.transactor_id == transactor_id)
        
        if direction:
            logger.debug(f"[PATTERN_DISCOVERY] Filtering by direction: {direction}")
            stmt = stmt.where(Transaction.type == direction)
        
        # Group and count
        stmt = stmt.group_by(
            Transaction.transactor_id,
            Transaction.type,
            Transaction.currency_id
        ).having(
            func.count(Transaction.id) >= DeterministicPatternDiscovery.MIN_TRANSACTIONS_REQUIRED
        )
        
        result = await self.db.execute(stmt)
        groups = result.all()
        
        logger.info(f"[PATTERN_DISCOVERY] Query returned {len(groups)} groups (before MIN_TRANSACTIONS filter)")
        for idx, group in enumerate(groups, 1):
            logger.debug(f"[PATTERN_DISCOVERY] Group {idx}: transactor={group.transactor_id}, "
                        f"direction={group.direction}, currency={group.currency_id}, count={group.count}")
        
        if len(groups) == 0:
            logger.warning(f"[PATTERN_DISCOVERY] No transaction groups found. Check: "
                          f"1) User has transactions, "
                          f"2) Transactions have transactor_id, "
                          f"3) At least {DeterministicPatternDiscovery.MIN_TRANSACTIONS_REQUIRED} transactions per (transactor, direction, currency), "
                          f"4) Direction filter matches actual transaction.type values (expense/income/refund)")
        
        return [
            {
                'transactor_id': r.transactor_id,
                'direction': r.direction,
                'currency_id': r.currency_id
            }
            for r in groups
        ]
    
    async def _discover_patterns_for_group(
        self,
        user_id: uuid.UUID,
        transactor_id: uuid.UUID,
        direction: str,
        currency_id: uuid.UUID
    ) -> List[Dict]:
        """
        Discover patterns for a single (transactor, direction, currency) group.
        Only processes transactions NOT already linked to any pattern.
        """
        logger.debug(f"[PATTERN_DISCOVERY] Analyzing group: transactor={transactor_id}, direction={direction}")
        
        # Fetch transactions for this group, sorted by date
        stmt = select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.transactor_id == transactor_id,
            Transaction.type == direction,
            Transaction.currency_id == currency_id
        ).order_by(Transaction.date.asc())
        
        result = await self.db.execute(stmt)
        all_transactions = result.scalars().all()
        
        logger.debug(f"[PATTERN_DISCOVERY] Found {len(all_transactions)} total transactions for this group")
        
        # Get already-linked transaction IDs to exclude them from discovery
        linked_result = await self.db.execute(
            select(PatternTransaction.transaction_id)
            .where(PatternTransaction.transaction_id.in_([t.id for t in all_transactions]))
        )
        linked_ids = {row[0] for row in linked_result.all()}
        
        # Filter to only unassigned transactions
        transactions = [t for t in all_transactions if t.id not in linked_ids]
        
        logger.info(f"[PATTERN_DISCOVERY] After filtering linked transactions: {len(transactions)} unassigned, "
                   f"{len(linked_ids)} already linked, {len(all_transactions)} total")
        
        if len(transactions) < DeterministicPatternDiscovery.MIN_TRANSACTIONS_REQUIRED:
            logger.debug(f"[PATTERN_DISCOVERY] Not enough transactions ({len(transactions)} < {DeterministicPatternDiscovery.MIN_TRANSACTIONS_REQUIRED}), skipping")
            return []
        
        # Convert to discovery format
        discovery_txns = [
            DiscoveryTransaction(
                txn_id=str(t.id),
                txn_date=t.date,
                amount=t.amount
            )
            for t in transactions
        ]
        
        # Run deterministic discovery
        logger.info(f"[PATTERN_DISCOVERY] Running deterministic discovery on {len(discovery_txns)} transactions")
        engine = DeterministicPatternDiscovery(discovery_txns)
        candidates = engine.discover_patterns()
        
        logger.info(f"[PATTERN_DISCOVERY] Discovery engine found {len(candidates)} pattern candidates")
        
        if not candidates:
            logger.debug(f"[PATTERN_DISCOVERY] No patterns found for this group")
            return []
        
        # Get transactor and currency info
        transactor_result = await self.db.execute(
            select(Transactor).where(Transactor.id == transactor_id)
        )
        transactor = transactor_result.scalar_one_or_none()
        
        currency_result = await self.db.execute(
            select(Currency).where(Currency.id == currency_id)
        )
        currency = currency_result.scalar_one_or_none()
        
        # Process each candidate
        discovered = []
        for idx, candidate in enumerate(candidates, 1):
            logger.debug(f"[PATTERN_DISCOVERY] Processing candidate {idx}/{len(candidates)}: "
                        f"case={candidate.pattern_case.value}, interval={candidate.interval_days}d, "
                        f"confidence={candidate.confidence:.2f}")
            
            # Get LLM explanation
            logger.debug(f"[PATTERN_DISCOVERY] Requesting LLM explanation for candidate {idx}")
            explanation = self.explanation_agent.explain_pattern(
                transactor_name=transactor.name if transactor else "Unknown",
                pattern_case=candidate.pattern_case,
                interval_days=candidate.interval_days,
                amount_behavior=candidate.amount_behavior,
                avg_amount=candidate.cluster.avg_amount,
                min_amount=candidate.cluster.min_amount,
                max_amount=candidate.cluster.max_amount,
                confidence=candidate.confidence,
                observation_count=len(candidate.transactions),
                currency_symbol=self._get_currency_symbol(currency.value if currency else "INR")
            )
            
            # Skip if LLM marks as invalid
            if not explanation.get('is_valid', True):
                logger.warning(f"[PATTERN_DISCOVERY] LLM marked candidate {idx} as invalid, skipping")
                continue
            
            logger.info(f"[PATTERN_DISCOVERY] LLM validated candidate {idx}, saving to database")
            
            # Save to database
            pattern = await self._save_pattern(
                user_id=user_id,
                transactor_id=transactor_id,
                direction=direction,
                currency_id=currency_id,
                candidate=candidate,
                explanation=explanation
            )
            
            discovered.append({
                'pattern': pattern,
                'transactor': transactor,  # Include transactor object to avoid lazy loading
                'explanation': explanation,
                'transactions': candidate.transactions
            })
        
        return discovered
    
    async def _save_pattern(
        self,
        user_id: uuid.UUID,
        transactor_id: uuid.UUID,
        direction: str,
        currency_id: uuid.UUID,
        candidate: PatternCandidate,
        explanation: Dict
    ) -> RecurringPattern:
        """
        Save discovered pattern to database.
        Creates pattern, streak, initial obligation, and links transactions.
        """
        logger.debug(f"[PATTERN_SAVE] Checking for existing pattern: user={user_id}, transactor={transactor_id}, direction={direction}")
        
        # Check if pattern already exists
        existing_result = await self.db.execute(
            select(RecurringPattern).where(
                RecurringPattern.user_id == user_id,
                RecurringPattern.transactor_id == transactor_id,
                RecurringPattern.direction == direction
            )
        )
        existing = existing_result.scalar_one_or_none()
        
        if existing:
            # Update existing pattern
            logger.info(f"[PATTERN_SAVE] Updating existing pattern {existing.id}, incrementing version to {existing.detection_version + 1}")
            existing.pattern_type = self._map_pattern_case_to_type(candidate.pattern_case)
            existing.interval_days = candidate.interval_days or 30
            existing.amount_behavior = candidate.amount_behavior.value
            existing.confidence = Decimal(str(candidate.confidence))
            existing.status = 'ACTIVE'
            existing.detected_at = datetime.utcnow()
            existing.last_evaluated_at = datetime.utcnow()
            existing.detection_version += 1
            pattern = existing
        else:
            # Create new pattern
            logger.info(f"[PATTERN_SAVE] Creating new pattern for transactor {transactor_id}")
            pattern = RecurringPattern(
                id=uuid.uuid4(),
                user_id=user_id,
                transactor_id=transactor_id,
                direction=direction,
                pattern_type=self._map_pattern_case_to_type(candidate.pattern_case),
                interval_days=candidate.interval_days or 30,
                amount_behavior=candidate.amount_behavior.value,
                status='ACTIVE',
                confidence=Decimal(str(candidate.confidence)),
                detected_at=datetime.utcnow(),
                last_evaluated_at=datetime.utcnow(),
                detection_version=1
            )
            self.db.add(pattern)
        
        await self.db.flush()
        
        # Create or update streak
        streak_result = await self.db.execute(
            select(RecurringPatternStreak).where(
                RecurringPatternStreak.recurring_pattern_id == pattern.id
            )
        )
        streak = streak_result.scalar_one_or_none()
        
        last_txn_date = candidate.transactions[-1].txn_date
        
        if not streak:
            logger.debug(f"[PATTERN_SAVE] Creating new streak record with {len(candidate.transactions)} transactions")
            streak = RecurringPatternStreak(
                recurring_pattern_id=pattern.id,
                current_streak_count=len(candidate.transactions),
                longest_streak_count=len(candidate.transactions),
                last_actual_date=last_txn_date,
                last_expected_date=last_txn_date,
                missed_count=0,
                confidence_multiplier=Decimal('1.0')
            )
            self.db.add(streak)
        else:
            logger.debug(f"[PATTERN_SAVE] Updating existing streak record")
            streak.current_streak_count = len(candidate.transactions)
            streak.longest_streak_count = max(streak.longest_streak_count, len(candidate.transactions))
            streak.last_actual_date = last_txn_date
            streak.confidence_multiplier = Decimal('1.0')
        
        await self.db.flush()
        
        # Link transactions to pattern
        for txn in candidate.transactions:
            # Check if already linked
            existing_link_result = await self.db.execute(
                select(PatternTransaction).where(
                    PatternTransaction.recurring_pattern_id == pattern.id,
                    PatternTransaction.transaction_id == uuid.UUID(txn.txn_id)
                )
            )
            existing_link = existing_link_result.scalar_one_or_none()
            
            if not existing_link:
                link = PatternTransaction(
                    id=uuid.uuid4(),
                    recurring_pattern_id=pattern.id,
                    transaction_id=uuid.UUID(txn.txn_id),
                    linked_at=datetime.utcnow()
                )
                self.db.add(link)
        
        # Create initial obligation
        logger.debug(f"[PATTERN_SAVE] Creating initial obligation for pattern {pattern.id}")
        await self._create_next_obligation(pattern, candidate)
        
        await self.db.commit()
        
        # Refresh to load relationships
        await self.db.refresh(pattern, ['transactor'])
        
        logger.info(f"[PATTERN_SAVE] Successfully saved pattern {pattern.id} with {len(candidate.transactions)} linked transactions")
        
        return pattern
    
    def _map_pattern_case_to_type(self, case: PatternCase) -> str:
        """Map PatternCase enum to database pattern_type"""
        mapping = {
            PatternCase.FIXED_MONTHLY: 'MONTHLY',
            PatternCase.VARIABLE_MONTHLY: 'MONTHLY',
            PatternCase.FLEXIBLE_MONTHLY: 'MONTHLY',
            PatternCase.BI_MONTHLY: 'BIWEEKLY',  # Closest match
            PatternCase.QUARTERLY: 'QUARTERLY',
            PatternCase.CUSTOM_INTERVAL: 'MONTHLY',  # Default
        }
        return mapping.get(case, 'MONTHLY')
    
    async def _create_next_obligation(
        self,
        pattern: RecurringPattern,
        candidate: PatternCandidate
    ) -> PatternObligation:
        """Create next expected obligation for pattern"""
        # Create pattern state
        state = PatternObligationManager.create_initial_state(
            pattern_id=str(pattern.id),
            pattern_case=candidate.pattern_case,
            interval_days=candidate.interval_days,
            amount_behavior=candidate.amount_behavior,
            last_transaction_date=candidate.transactions[-1].txn_date,
            initial_confidence=candidate.confidence
        )
        
        # Estimate amount range
        recent_amounts = [t.amount for t in candidate.transactions[-3:]]
        min_amt, max_amt = PatternObligationManager.estimate_amount_range(
            recent_amounts,
            candidate.amount_behavior
        )
        
        # Create obligation
        obligation_obj = PatternObligationManager.create_obligation_from_state(
            state=state,
            expected_min_amount=min_amt,
            expected_max_amount=max_amt
        )
        
        # Save to DB
        db_obligation = PatternObligation(
            id=uuid.uuid4(),
            recurring_pattern_id=pattern.id,
            expected_date=obligation_obj.expected_date,
            tolerance_days=Decimal(str(obligation_obj.tolerance_days)),
            expected_min_amount=obligation_obj.expected_min_amount,
            expected_max_amount=obligation_obj.expected_max_amount,
            status='EXPECTED'
        )
        self.db.add(db_obligation)
        await self.db.flush()
        
        return db_obligation
    
    # ===== PATTERN RETRIEVAL =====
    
    async def get_user_patterns(
        self,
        user_id: uuid.UUID,
        status: Optional[str] = None,
        include_obligations: bool = True
    ) -> List[Dict]:
        """
        Get all patterns for a user with optional filtering.
        """
        stmt = select(RecurringPattern).where(
            RecurringPattern.user_id == user_id
        )
        
        if status:
            stmt = stmt.where(RecurringPattern.status == status)
        
        stmt = stmt.order_by(desc(RecurringPattern.confidence))
        
        result = await self.db.execute(stmt)
        patterns = result.scalars().all()
        
        result = []
        for pattern in patterns:
            pattern_dict = pattern.to_dict()
            
            # Add transactor info
            if pattern.transactor:
                pattern_dict['transactor'] = {
                    'id': str(pattern.transactor.id),
                    'name': pattern.transactor.name
                }
            
            # Add streak info
            if pattern.streak:
                pattern_dict['streak'] = pattern.streak.to_dict()
            
            # Add obligations
            if include_obligations:
                obligations = await self.get_pattern_obligations(pattern.id)
                pattern_dict['obligations'] = obligations
            
            result.append(pattern_dict)
        
        return result
    
    async def get_pattern_obligations(
        self,
        pattern_id: uuid.UUID,
        status: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict]:
        """Get obligations for a specific pattern"""
        stmt = select(PatternObligation).where(
            PatternObligation.recurring_pattern_id == pattern_id
        )
        
        if status:
            stmt = stmt.where(PatternObligation.status == status)
        
        stmt = stmt.order_by(desc(PatternObligation.expected_date)).limit(limit)
        
        result = await self.db.execute(stmt)
        obligations = result.scalars().all()
        return [obl.to_dict() for obl in obligations]
    
    async def get_upcoming_obligations(
        self,
        user_id: uuid.UUID,
        days_ahead: int = 30
    ) -> List[Dict]:
        """Get all upcoming obligations for a user"""
        cutoff_date = datetime.utcnow() + timedelta(days=days_ahead)
        
        stmt = select(PatternObligation).join(
            RecurringPattern
        ).where(
            RecurringPattern.user_id == user_id,
            PatternObligation.status == 'EXPECTED',
            PatternObligation.expected_date <= cutoff_date
        ).order_by(PatternObligation.expected_date)
        
        result = await self.db.execute(stmt)
        obligations = result.scalars().all()
        
        result = []
        for obl in obligations:
            obl_dict = obl.to_dict()
            obl_dict['pattern'] = obl.pattern.to_dict() if obl.pattern else None
            obl_dict['transactor'] = {
                'id': str(obl.pattern.transactor.id),
                'name': obl.pattern.transactor.name
            } if obl.pattern and obl.pattern.transactor else None
            result.append(obl_dict)
        
        return result
    
    # ===== INCREMENTAL UPDATES =====
    
    async def process_new_transaction(
        self,
        transaction_id: uuid.UUID
    ) -> Dict:
        """
        Process a new transaction against active patterns.
        Called after transaction is inserted.
        
        This performs:
        1. Lazy miss detection (check for overdue obligations)
        2. Transaction matching against active patterns
        3. State updates if matched
        
        NO PATTERN DISCOVERY happens in this flow.
        """
        logger.info(f"[PATTERN_MATCH] Processing new transaction {transaction_id}")
        
        # Get transaction
        txn_result = await self.db.execute(
            select(Transaction).where(Transaction.id == transaction_id)
        )
        transaction = txn_result.scalar_one_or_none()
        
        if not transaction or not transaction.transactor_id:
            logger.warning(f"[PATTERN_MATCH] Transaction {transaction_id} not found or has no transactor")
            return {'matched': False, 'reason': 'No transactor'}
        
        # Get active patterns for this (user, transactor, direction, currency)
        logger.debug(f"[PATTERN_MATCH] Looking for active patterns: user={transaction.user_id}, "
                    f"transactor={transaction.transactor_id}, direction={transaction.type}")
        
        patterns_result = await self.db.execute(
            select(RecurringPattern).where(
                RecurringPattern.user_id == transaction.user_id,
                RecurringPattern.transactor_id == transaction.transactor_id,
                RecurringPattern.direction == transaction.type,
                RecurringPattern.status.in_(['ACTIVE', 'PAUSED'])
            )
        )
        patterns = patterns_result.scalars().all()
        
        logger.info(f"[PATTERN_MATCH] Found {len(patterns)} active patterns to check")
        
        if not patterns:
            logger.debug(f"[PATTERN_MATCH] No active patterns found for this transaction")
            return {'matched': False, 'reason': 'No active patterns'}
        
        # Process against each pattern
        current_date = datetime.utcnow()
        matches = []
        
        for pattern in patterns:
            # Get pattern state
            streak = pattern.streak
            if not streak:
                continue
            
            state = PatternState(
                pattern_id=str(pattern.id),
                pattern_case=PatternCase[pattern.pattern_type] if hasattr(PatternCase, pattern.pattern_type) else PatternCase.FIXED_MONTHLY,
                interval_days=pattern.interval_days,
                amount_behavior=AmountBehaviorType[pattern.amount_behavior],
                last_actual_date=streak.last_actual_date,
                next_expected_date=streak.last_expected_date,
                status=pattern.status,
                current_streak=streak.current_streak_count,
                missed_count=streak.missed_count,
                confidence_multiplier=float(streak.confidence_multiplier)
            )
            
            # Check match
            results = TransactionProcessor.process_transaction(
                transaction_date=transaction.date,
                transaction_amount=transaction.amount,
                active_patterns=[state],
                current_date=current_date
            )
            
            for updated_state, was_matched in results:
                if was_matched:
                    logger.info(f"[PATTERN_MATCH] Transaction matched pattern {pattern.id}")
                    # Update database
                    await self._apply_state_update(pattern, updated_state, transaction)
                    matches.append({
                        'pattern_id': str(pattern.id),
                        'matched': True
                    })
                else:
                    logger.debug(f"[PATTERN_MATCH] Transaction did not match pattern {pattern.id}")
        
        await self.db.commit()
        logger.info(f"[PATTERN_MATCH] Processing complete: {len(matches)} matches found")
        
        return {
            'matched': len(matches) > 0,
            'matches': matches
        }
    
    async def _apply_state_update(
        self,
        pattern: RecurringPattern,
        state: PatternState,
        transaction: Transaction
    ):
        """Apply state updates to database"""
        logger.debug(f"[PATTERN_UPDATE] Applying state update for pattern {pattern.id}")
        
        # Update streak
        streak = pattern.streak
        if streak:
            streak.current_streak_count = state.current_streak
            streak.longest_streak_count = max(streak.longest_streak_count, state.current_streak)
            streak.last_actual_date = state.last_actual_date
            streak.last_expected_date = state.next_expected_date
            streak.missed_count = state.missed_count
            streak.confidence_multiplier = Decimal(str(state.confidence_multiplier))
        
        # Update pattern
        pattern.status = state.status
        pattern.last_evaluated_at = datetime.utcnow()
        
        # Mark obligation as fulfilled
        pending_obl_result = await self.db.execute(
            select(PatternObligation).where(
                PatternObligation.recurring_pattern_id == pattern.id,
                PatternObligation.status == 'EXPECTED'
            ).order_by(PatternObligation.expected_date)
        )
        pending_obligation = pending_obl_result.scalars().first()
        
        if pending_obligation:
            days_early = (pending_obligation.expected_date - transaction.date).days
            logger.info(f"[PATTERN_UPDATE] Fulfilling obligation {pending_obligation.id}, "
                       f"expected: {pending_obligation.expected_date}, actual: {transaction.date}, "
                       f"days_early: {days_early}")
            pending_obligation.status = 'FULFILLED'
            pending_obligation.fulfilled_by_transaction_id = transaction.id
            pending_obligation.fulfilled_at = transaction.date
            pending_obligation.days_early = Decimal(str(days_early))
        else:
            logger.warning(f"[PATTERN_UPDATE] No pending obligation found for pattern {pattern.id}")
        
        # Create next obligation
        await self._create_next_obligation_from_state(pattern, state)
        
        # Link transaction
        link = PatternTransaction(
            id=uuid.uuid4(),
            recurring_pattern_id=pattern.id,
            transaction_id=transaction.id,
            linked_at=datetime.utcnow()
        )
        self.db.add(link)
    
    async def _create_next_obligation_from_state(
        self,
        pattern: RecurringPattern,
        state: PatternState
    ):
        """Create next obligation from updated state"""
        # Get recent transaction amounts for estimation
        recent_txns_result = await self.db.execute(
            select(Transaction).join(
                PatternTransaction
            ).where(
                PatternTransaction.recurring_pattern_id == pattern.id
            ).order_by(desc(Transaction.date)).limit(3)
        )
        recent_txns = recent_txns_result.scalars().all()
        
        recent_amounts = [t.amount for t in recent_txns]
        min_amt, max_amt = PatternObligationManager.estimate_amount_range(
            recent_amounts,
            state.amount_behavior
        )
        
        obligation_obj = PatternObligationManager.create_obligation_from_state(
            state=state,
            expected_min_amount=min_amt,
            expected_max_amount=max_amt
        )
        
        db_obligation = PatternObligation(
            id=uuid.uuid4(),
            recurring_pattern_id=pattern.id,
            expected_date=obligation_obj.expected_date,
            tolerance_days=Decimal(str(obligation_obj.tolerance_days)),
            expected_min_amount=obligation_obj.expected_min_amount,
            expected_max_amount=obligation_obj.expected_max_amount,
            status='EXPECTED'
        )
        self.db.add(db_obligation)
