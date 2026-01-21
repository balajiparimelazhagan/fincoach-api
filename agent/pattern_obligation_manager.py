"""
Pattern Obligation Manager

Implements Steps 10-15: Safe next-obligation computation and state management.
Stateful, interval-based, cannot drift.
"""
from datetime import datetime, timedelta
from typing import Optional, Tuple
from decimal import Decimal
from dataclasses import dataclass
from enum import Enum
from calendar import monthrange

from app.logging_config import get_logger

logger = get_logger(__name__)

from agent.pattern_discovery_engine import PatternCase, AmountBehaviorType


class ObligationStatus(Enum):
    """Obligation lifecycle states"""
    EXPECTED = "EXPECTED"
    FULFILLED = "FULFILLED"
    MISSED = "MISSED"
    CANCELLED = "CANCELLED"


@dataclass
class PatternState:
    """
    Persistent state for a recurring pattern.
    This is what gets stored in the database.
    """
    pattern_id: str
    pattern_case: PatternCase
    interval_days: Optional[int]
    amount_behavior: AmountBehaviorType
    last_actual_date: datetime
    next_expected_date: datetime
    status: str  # ACTIVE, PAUSED, BROKEN
    current_streak: int
    missed_count: int
    confidence_multiplier: float


@dataclass
class Obligation:
    """Represents a single expected obligation"""
    pattern_id: str
    expected_date: datetime
    tolerance_days: float
    expected_min_amount: Optional[Decimal]
    expected_max_amount: Optional[Decimal]
    status: ObligationStatus


class PatternObligationManager:
    """
    Manages pattern state and obligation computation.
    
    Key principles:
    - State is authoritative (never recompute from history)
    - Next obligation computed from state, not averages
    - Missing one payment does not destroy pattern
    - State machine prevents drift
    """
    
    # State transition thresholds
    MAX_MISSED_FOR_ACTIVE = 1
    MAX_MISSED_FOR_PAUSED = 3
    CONFIDENCE_DECAY_PER_MISS = 0.15
    CONFIDENCE_BOOST_PER_FULFILL = 0.05
    
    def __init__(self):
        pass
    
    # ===== STEP 10: Persist pattern state =====
    
    @staticmethod
    def create_initial_state(
        pattern_id: str,
        pattern_case: PatternCase,
        interval_days: Optional[int],
        amount_behavior: AmountBehaviorType,
        last_transaction_date: datetime,
        initial_confidence: float
    ) -> PatternState:
        """
        Step 10: Create initial pattern state after discovery.
        """
        logger.debug(f"[OBLIGATION_MGR] Step 10: Creating initial state for pattern {pattern_id}")
        
        # Compute first next expected date
        next_expected = PatternObligationManager._compute_next_expected_date(
            pattern_case=pattern_case,
            interval_days=interval_days,
            last_actual_date=last_transaction_date
        )
        
        logger.info(f"[OBLIGATION_MGR] Initial state: next_expected={next_expected.date()}, "
                   f"case={pattern_case.value}, interval={interval_days}d")
        
        return PatternState(
            pattern_id=pattern_id,
            pattern_case=pattern_case,
            interval_days=interval_days,
            amount_behavior=amount_behavior,
            last_actual_date=last_transaction_date,
            next_expected_date=next_expected,
            status='ACTIVE',
            current_streak=1,  # Start with 1 (the last transaction)
            missed_count=0,
            confidence_multiplier=1.0
        )
    
    # ===== STEP 11: Compute next expected obligation date =====
    
    @staticmethod
    def _compute_next_expected_date(
        pattern_case: PatternCase,
        interval_days: Optional[int],
        last_actual_date: datetime
    ) -> datetime:
        """
        Step 11: Compute next expected date based on pattern case.
        CRITICAL: This is deterministic and state-based.
        """
        logger.debug(f"[OBLIGATION_MGR] Step 11: Computing next expected date, case={pattern_case.value}, interval={interval_days}d")
        if pattern_case == PatternCase.FLEXIBLE_MONTHLY:
            # Next calendar month start
            if last_actual_date.month == 12:
                next_month_start = datetime(last_actual_date.year + 1, 1, 1)
            else:
                next_month_start = datetime(last_actual_date.year, last_actual_date.month + 1, 1)
            return next_month_start
        
        elif pattern_case in [PatternCase.FIXED_MONTHLY, PatternCase.VARIABLE_MONTHLY,
                             PatternCase.BI_MONTHLY, PatternCase.QUARTERLY,
                             PatternCase.CUSTOM_INTERVAL]:
            # Fixed interval from last actual date
            if interval_days is None:
                raise ValueError(f"interval_days required for {pattern_case}")
            return last_actual_date + timedelta(days=interval_days)
        
        elif pattern_case == PatternCase.FREQUENT_VARIABLE:
            # Should not compute obligations for frequent variable
            raise ValueError("Cannot compute obligations for FREQUENT_VARIABLE patterns")
        
        else:
            raise ValueError(f"Unknown pattern case: {pattern_case}")
    
    # ===== STEP 12: Define safe tolerance window =====
    
    @staticmethod
    def compute_tolerance_window(
        pattern_case: PatternCase,
        interval_days: Optional[int]
    ) -> float:
        """
        Step 12: Compute tolerance window (in days) for obligation matching.
        """
        if pattern_case == PatternCase.FIXED_MONTHLY or pattern_case == PatternCase.VARIABLE_MONTHLY:
            tolerance = 3.0  # ±3 days
        elif pattern_case == PatternCase.FLEXIBLE_MONTHLY:
            # Entire calendar month is acceptable
            tolerance = 31.0
        elif pattern_case == PatternCase.BI_MONTHLY or pattern_case == PatternCase.QUARTERLY:
            tolerance = 5.0  # ±5 days
        elif pattern_case == PatternCase.CUSTOM_INTERVAL:
            if interval_days is None:
                tolerance = 3.0
            else:
                tolerance = max(2.0, interval_days * 0.1)  # 10% of interval or 2 days minimum
        else:
            tolerance = 3.0  # Default
        
        logger.debug(f"[OBLIGATION_MGR] Step 12: Tolerance window for {pattern_case.value}: ±{tolerance} days")
        return tolerance
    
    # ===== STEP 13: Obligation matching (when new transaction arrives) =====
    
    @staticmethod
    def check_obligation_match(
        transaction_date: datetime,
        expected_date: datetime,
        tolerance_days: float
    ) -> Tuple[bool, float]:
        """
        Step 13: Check if transaction fulfills expected obligation.
        
        Returns:
            (is_match, days_early)
            days_early is positive if early, negative if late
        """
        days_diff = (expected_date - transaction_date).days
        
        logger.debug(f"[OBLIGATION_MGR] Step 13: Checking obligation match, days_diff={days_diff}, tolerance=±{tolerance_days}")
        
        if abs(days_diff) <= tolerance_days:
            logger.debug(f"[OBLIGATION_MGR] Transaction matches obligation (days_early={days_diff})")
            return (True, days_diff)
        else:
            logger.debug(f"[OBLIGATION_MGR] Transaction does not match obligation (outside tolerance)")
            return (False, days_diff)
    
    # ===== STEP 14: Advance obligation state (safe) =====
    
    @staticmethod
    def fulfill_obligation(
        state: PatternState,
        actual_transaction_date: datetime,
        days_early: float
    ) -> PatternState:
        """
        Step 14: Advance pattern state when obligation is fulfilled.
        This is the ONLY way to move state forward.
        """
        # Update state
        state.last_actual_date = actual_transaction_date
        state.current_streak += 1
        state.missed_count = 0  # Reset misses on successful fulfillment
        
        # Boost confidence slightly
        state.confidence_multiplier = min(1.0, state.confidence_multiplier + PatternObligationManager.CONFIDENCE_BOOST_PER_FULFILL)
        
        # Compute next expected date
        state.next_expected_date = PatternObligationManager._compute_next_expected_date(
            pattern_case=state.pattern_case,
            interval_days=state.interval_days,
            last_actual_date=actual_transaction_date
        )
        
        # Ensure status is ACTIVE if it was PAUSED
        if state.status == 'PAUSED':
            state.status = 'ACTIVE'
        
        return state
    
    # ===== STEP 15: Miss handling (safe degradation) =====
    
    @staticmethod
    def handle_missed_obligation(
        state: PatternState,
        current_date: datetime
    ) -> PatternState:
        """
        Step 15: Handle missed obligation with safe degradation.
        
        Called when: current_date > next_expected_date + tolerance
        """
        state.missed_count += 1
        logger.warning(f"[OBLIGATION_MGR] Step 15: Missed obligation detected, missed_count={state.missed_count}")
        
        # Decay confidence
        old_confidence = state.confidence_multiplier
        state.confidence_multiplier = max(0.0, state.confidence_multiplier - PatternObligationManager.CONFIDENCE_DECAY_PER_MISS)
        logger.debug(f"[OBLIGATION_MGR] Confidence decay: {old_confidence:.2f} -> {state.confidence_multiplier:.2f}")
        
        # State transitions
        if state.missed_count <= PatternObligationManager.MAX_MISSED_FOR_ACTIVE:
            state.status = 'ACTIVE'  # Still active, but degraded
            logger.info(f"[OBLIGATION_MGR] Pattern remains ACTIVE")
        elif state.missed_count <= PatternObligationManager.MAX_MISSED_FOR_PAUSED:
            state.status = 'PAUSED'  # Paused, waiting for recovery
            logger.warning(f"[OBLIGATION_MGR] Pattern degraded to PAUSED")
        else:
            state.status = 'BROKEN'  # Too many misses
            logger.error(f"[OBLIGATION_MGR] Pattern marked as BROKEN")
        
        # Advance expected date (even when missed)
        # This prevents cascading miss detection
        state.next_expected_date = PatternObligationManager._compute_next_expected_date(
            pattern_case=state.pattern_case,
            interval_days=state.interval_days,
            last_actual_date=state.last_actual_date  # Use last ACTUAL, not expected
        )
        
        # DO NOT delete pattern - keep for history
        
        return state
    
    # ===== OBLIGATION CREATION =====
    
    @staticmethod
    def create_obligation_from_state(
        state: PatternState,
        expected_min_amount: Optional[Decimal] = None,
        expected_max_amount: Optional[Decimal] = None
    ) -> Obligation:
        """
        Create an obligation from current pattern state.
        """
        tolerance = PatternObligationManager.compute_tolerance_window(
            state.pattern_case,
            state.interval_days
        )
        
        logger.debug(f"[OBLIGATION_MGR] Creating obligation: expected_date={state.next_expected_date.date()}, "
                    f"tolerance=±{tolerance}d, amount_range=[{expected_min_amount}, {expected_max_amount}]")
        
        return Obligation(
            pattern_id=state.pattern_id,
            expected_date=state.next_expected_date,
            tolerance_days=tolerance,
            expected_min_amount=expected_min_amount,
            expected_max_amount=expected_max_amount,
            status=ObligationStatus.EXPECTED
        )
    
    # ===== CHECK FOR OVERDUE OBLIGATIONS =====
    
    @staticmethod
    def is_obligation_overdue(
        next_expected_date: datetime,
        tolerance_days: float,
        current_date: datetime
    ) -> bool:
        """
        Check if an obligation is overdue (past tolerance window).
        """
        deadline = next_expected_date + timedelta(days=tolerance_days)
        return current_date > deadline
    
    # ===== AMOUNT RANGE ESTIMATION =====
    
    @staticmethod
    def estimate_amount_range(
        recent_amounts: list[Decimal],
        amount_behavior: AmountBehaviorType
    ) -> Tuple[Decimal, Decimal]:
        """
        Estimate expected amount range for next obligation.
        Used for budgeting/forecasting, NOT for matching.
        """
        if not recent_amounts:
            logger.debug(f"[OBLIGATION_MGR] No recent amounts for estimation")
            return (Decimal('0'), Decimal('0'))
        
        avg = sum(recent_amounts) / len(recent_amounts)
        logger.debug(f"[OBLIGATION_MGR] Estimating amount range: behavior={amount_behavior.value}, avg={avg:.2f}, n={len(recent_amounts)}")
        
        if amount_behavior == AmountBehaviorType.FIXED:
            # Tight range
            margin = avg * Decimal('0.05')  # ±5%
        elif amount_behavior == AmountBehaviorType.VARIABLE:
            # Moderate range
            margin = avg * Decimal('0.30')  # ±30%
        else:  # HIGHLY_VARIABLE
            # Wide range
            margin = avg * Decimal('0.50')  # ±50%
        
        return (
            max(Decimal('0'), avg - margin),
            avg + margin
        )


# ===== TRANSACTION PROCESSOR =====

class TransactionProcessor:
    """
    Processes incoming transactions against active patterns.
    Handles obligation matching and state updates.
    """
    
    @staticmethod
    def process_transaction(
        transaction_date: datetime,
        transaction_amount: Decimal,
        active_patterns: list[PatternState],
        current_date: datetime
    ) -> list[Tuple[PatternState, bool]]:
        """
        Process a new transaction against all active patterns.
        
        Returns:
            List of (updated_state, was_matched) tuples
        """
        logger.debug(f"[TRANSACTION_PROCESSOR] Processing transaction: date={transaction_date.date()}, "
                    f"amount={transaction_amount:.2f}, against {len(active_patterns)} patterns")
        
        results = []
        
        for idx, state in enumerate(active_patterns, 1):
            logger.debug(f"[TRANSACTION_PROCESSOR] Checking pattern {idx}/{len(active_patterns)}: "
                        f"pattern_id={state.pattern_id}, expected={state.next_expected_date.date()}")
            # Check if transaction fulfills this pattern's obligation
            tolerance = PatternObligationManager.compute_tolerance_window(
                state.pattern_case,
                state.interval_days
            )
            
            is_match, days_early = PatternObligationManager.check_obligation_match(
                transaction_date=transaction_date,
                expected_date=state.next_expected_date,
                tolerance_days=tolerance
            )
            
            if is_match:
                # Fulfill obligation
                logger.info(f"[TRANSACTION_PROCESSOR] Transaction matched pattern {idx}, fulfilling obligation")
                updated_state = PatternObligationManager.fulfill_obligation(
                    state=state,
                    actual_transaction_date=transaction_date,
                    days_early=days_early
                )
                results.append((updated_state, True))
            else:
                # No match - check if obligation is overdue
                logger.debug(f"[TRANSACTION_PROCESSOR] Transaction did not match pattern {idx}")
                if PatternObligationManager.is_obligation_overdue(
                    state.next_expected_date,
                    tolerance,
                    current_date
                ):
                    # Handle missed obligation
                    updated_state = PatternObligationManager.handle_missed_obligation(
                        state=state,
                        current_date=current_date
                    )
                    results.append((updated_state, False))
                else:
                    # No match yet, but not overdue - keep waiting
                    results.append((state, False))
        
        return results
