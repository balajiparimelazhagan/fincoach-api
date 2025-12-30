"""
Streak Service: Pure deterministic logic for tracking recurring pattern streaks.

No LLM, no configuration - just math and state machine logic.
Updates on EVERY new transaction.
"""

from typing import Optional
from datetime import datetime, timedelta
from decimal import Decimal
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.recurring_pattern_streak import RecurringPatternStreak
from app.models.recurring_pattern import RecurringPattern

logger = logging.getLogger(__name__)


class StreakService:
    """Service for tracking recurring pattern streaks over time."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def update_streak_for_transaction(
        self,
        pattern_id: str,
        transaction_date: datetime,
        interval_days: int,
        tolerance_days: int = 5
    ) -> Optional[RecurringPatternStreak]:
        """
        Update streak state for a single new transaction.
        
        This is pure deterministic logic, called on EVERY transaction.
        
        Args:
            pattern_id: UUID of recurring_pattern
            transaction_date: Date of new transaction
            interval_days: Expected interval from pattern (e.g., 30 for monthly)
            tolerance_days: Allowable deviation (default 5 days)
        
        Returns:
            Updated RecurringPatternStreak or None if pattern not found
        
        State Machine:
            1. If txn within expected window (±tolerance) → Streak continues, confidence +
            2. If txn late but acceptable → Streak paused, confidence -
            3. If txn way too late → Streak broken, confidence drops sharply
        """
        # Fetch current streak state
        result = await self.db.execute(
            select(RecurringPatternStreak)
            .where(RecurringPatternStreak.recurring_pattern_id == pattern_id)
        )
        streak = result.scalar_one_or_none()
        
        if not streak:
            logger.warning(f"Streak not found for pattern {pattern_id}")
            return None
        
        # Calculate expected window
        expected_date = streak.last_expected_date
        if not expected_date:
            # First transaction - no history
            logger.info(f"First transaction for pattern {pattern_id}, initializing streak")
            streak.current_streak_count = 1
            streak.longest_streak_count = 1
            streak.last_actual_date = transaction_date
            streak.last_expected_date = transaction_date + timedelta(days=interval_days)
            streak.confidence_multiplier = Decimal("1.0")
            streak.updated_at = datetime.utcnow()
            await self.db.commit()
            return streak
        
        window_start = expected_date - timedelta(days=tolerance_days)
        window_end = expected_date + timedelta(days=tolerance_days)
        
        logger.info(
            f"Streak update: pattern={pattern_id}, "
            f"txn_date={transaction_date}, "
            f"expected={expected_date}, "
            f"window=[{window_start}, {window_end}]"
        )
        
        # State machine logic
        if window_start <= transaction_date <= window_end:
            # ✅ On time (within tolerance)
            logger.info(f"Pattern {pattern_id}: Transaction on time")
            
            streak.current_streak_count += 1
            streak.longest_streak_count = max(streak.longest_streak_count, streak.current_streak_count)
            streak.last_actual_date = transaction_date
            streak.last_expected_date = transaction_date + timedelta(days=interval_days)
            streak.missed_count = 0  # Reset missed count
            
            # Confidence improvement (small increment for consistency)
            multiplier = float(streak.confidence_multiplier) + 0.05
            streak.confidence_multiplier = Decimal(str(min(1.0, multiplier)))
            
        elif transaction_date > window_start:
            # ⚠️  Late but within recovery window
            logger.warning(f"Pattern {pattern_id}: Transaction late (after expected window)")
            
            streak.current_streak_count += 1  # Still counts, but degraded
            streak.longest_streak_count = max(streak.longest_streak_count, streak.current_streak_count)
            streak.last_actual_date = transaction_date
            streak.last_expected_date = transaction_date + timedelta(days=interval_days)
            streak.missed_count += 1  # Count the miss
            
            # Confidence penalty (heavier for lateness)
            multiplier = float(streak.confidence_multiplier) - 0.1
            streak.confidence_multiplier = Decimal(str(max(0.0, multiplier)))
            
        else:
            # ❌ Way too late - streak broken
            logger.error(f"Pattern {pattern_id}: Streak broken (transaction too late)")
            
            # Reset streak but keep history
            streak.current_streak_count = 0
            streak.last_actual_date = transaction_date
            streak.last_expected_date = transaction_date + timedelta(days=interval_days)
            streak.missed_count += 1
            
            # Confidence drops sharply
            streak.confidence_multiplier = Decimal("0.3")
            
            # Update pattern status to BROKEN
            pattern = await self.db.get(RecurringPattern, pattern_id)
            if pattern:
                pattern.status = "BROKEN"
                logger.info(f"Pattern {pattern_id} marked as BROKEN due to missed transaction")
        
        # Update timestamp
        streak.updated_at = datetime.utcnow()
        await self.db.commit()
        
        logger.info(
            f"Streak updated: pattern={pattern_id}, "
            f"count={streak.current_streak_count}, "
            f"multiplier={streak.confidence_multiplier}"
        )
        
        return streak
    
    async def get_streak(self, pattern_id: str) -> Optional[RecurringPatternStreak]:
        """Fetch current streak state for a pattern."""
        result = await self.db.execute(
            select(RecurringPatternStreak)
            .where(RecurringPatternStreak.recurring_pattern_id == pattern_id)
        )
        return result.scalar_one_or_none()
    
    async def initialize_streak(
        self,
        pattern_id: str,
        first_transaction_date: datetime,
        interval_days: int
    ) -> RecurringPatternStreak:
        """
        Initialize streak state when pattern is first detected.
        
        Called ONCE per pattern, from pattern detection task.
        """
        streak = RecurringPatternStreak(
            recurring_pattern_id=pattern_id,
            current_streak_count=1,
            longest_streak_count=1,
            last_actual_date=first_transaction_date,
            last_expected_date=first_transaction_date + timedelta(days=interval_days),
            missed_count=0,
            confidence_multiplier=Decimal("1.0"),
            updated_at=datetime.utcnow()
        )
        self.db.add(streak)
        await self.db.commit()
        
        logger.info(f"Initialized streak for pattern {pattern_id}")
        return streak
    
    async def reset_streak(self, pattern_id: str) -> Optional[RecurringPatternStreak]:
        """
        Reset streak to initial state (when pattern status changes).
        
        Used when user manually pauses/unpauses a pattern.
        """
        streak = await self.get_streak(pattern_id)
        if streak:
            streak.current_streak_count = 0
            streak.missed_count = 0
            streak.confidence_multiplier = Decimal("1.0")
            streak.updated_at = datetime.utcnow()
            await self.db.commit()
            
            logger.info(f"Reset streak for pattern {pattern_id}")
        
        return streak
    
    def calculate_final_confidence(
        self,
        base_confidence: float,
        confidence_multiplier: Decimal
    ) -> float:
        """
        Calculate final user-facing confidence.
        
        Formula:
            final_confidence = base_confidence * confidence_multiplier
        
        Args:
            base_confidence: From detection (0.0-1.0)
            confidence_multiplier: From streak health (0.0-1.0)
        
        Returns:
            Final confidence clamped to [0.0, 1.0]
        """
        final = base_confidence * float(confidence_multiplier)
        return max(0.0, min(1.0, final))
