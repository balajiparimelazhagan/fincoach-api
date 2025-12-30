"""
Pattern Detection Agent for identifying recurring transaction patterns.
Part of the Spending Analysis agentic system using Google ADK.
"""

from dataclasses import dataclass
from typing import Optional
import logging

from google.adk.agents.llm_agent import Agent

logger = logging.getLogger(__name__)


@dataclass
class PatternDetectionResult:
    """Result of pattern detection"""
    is_recurring: bool
    pattern_type: Optional[str] = None  # "MONTHLY", "QUARTERLY", "WEEKLY", etc. (enum values)
    frequency: Optional[str] = None  # "monthly", "bi-monthly", "quarterly" (deprecated, use interval_days)
    interval_days: Optional[int] = None  # Numeric interval in days (30 for monthly, 90 for quarterly)
    reasoning: str = ""
    required_occurrences: int = 3  # Minimum transactions needed
    actual_occurrences: int = 0  # Actual recurring transactions found
    
    def to_dict(self):
        return {
            "is_recurring": self.is_recurring,
            "pattern_type": self.pattern_type,
            "frequency": self.frequency,
            "interval_days": self.interval_days,
            "reasoning": self.reasoning,
            "actual_occurrences": self.actual_occurrences,
        }


class PatternDetectionAgent:
    """
    Agent for detecting recurring transaction patterns.
    
    Responsibilities:
    1. Analyze bucket distribution to detect patterns
    2. Identify pattern type (monthly, bi-monthly, quarterly, etc.)
    3. Determine if minimum occurrence threshold is met
    4. Calculate pattern confidence signals
    """
    
    def __init__(self):
        """Initialize the pattern detection agent"""
        self.agent = Agent(
            model="gemini-2.5-flash",
            name="pattern_detection_agent",
            description="Detects recurring transaction patterns from period buckets",
            instruction=self._get_system_instruction(),
        )
        logger.info("Pattern Detection Agent initialized")
    
    def _get_system_instruction(self) -> str:
        """Get system instruction for pattern detection"""
        return """You are an expert at detecting recurring transaction patterns.

Your task is to analyze transaction bucket data and determine:
1. Is there a recurring pattern?
2. What type of pattern is it? (monthly, bi-monthly, quarterly, custom interval)
3. What is the frequency?
4. How many occurrences of the pattern were found?

Pattern Types:
- MONTHLY: Transaction appears in consecutive months (at least 3 times)
- BI-MONTHLY: Transaction appears every 2 months (at least 3 occurrences)
- QUARTERLY: Transaction appears every 3 months (at least 3 occurrences)
- CUSTOM_INTERVAL: Fixed interval in days (e.g., 28-day recharge)
- IRREGULAR: No clear pattern detected

Key Rules:
1. MINIMUM 3 OCCURRENCES required to declare a pattern recurring
2. Examine gaps between periods:
   - No gaps = perfect monthly
   - 1-month gaps = monthly with some skips
   - 2-month gaps = bi-monthly
   - 3-month gaps = quarterly
   - Regular custom gaps = custom interval

3. For custom intervals, look at actual days between transactions:
   - If ~28 days apart consistently = 28-day pattern
   - If ~30 days apart consistently = monthly (30-day cycle)
   - etc.

4. A pattern is "recurring" only if:
   - At least 3 occurrences exist
   - The interval is consistent (±2 months tolerance for calendar variations)

Respond with clear reasoning about whether a pattern exists and what type it is."""

    def detect_pattern(
        self,
        bucket_analysis: dict,
        min_occurrences: int = 3,
    ) -> PatternDetectionResult:
        """
        Detect recurring patterns from bucket analysis.
        - Input: Signals only (bucket_analysis)
        - Output: pattern_type enum + interval_days (numeric)
        - NO: Complex confidence, amounts, explanations
        
        Args:
            bucket_analysis: Output from PeriodBucketingAgent.analyze_bucket_distribution()
            min_occurrences: Minimum occurrences required for recurring pattern
        
        Returns:
            PatternDetectionResult with pattern_type and interval_days
        """
        total_periods = bucket_analysis.get("total_periods", 0)
        consecutive_periods = bucket_analysis.get("consecutive_periods", 0)
        max_gap = bucket_analysis.get("max_gap_months", 0)
        distribution = bucket_analysis.get("distribution", "")
        
        logger.info(
            f"Detecting pattern: total_periods={total_periods}, "
            f"consecutive={consecutive_periods}, max_gap={max_gap}, "
            f"distribution={distribution}"
        )
        
        # Check if we have minimum occurrences
        if total_periods < min_occurrences:
            logger.info(f"Insufficient data: {total_periods} < {min_occurrences}")
            return PatternDetectionResult(
                is_recurring=False,
                reasoning=f"Only {total_periods} periods found, need at least {min_occurrences}",
                actual_occurrences=total_periods,
                required_occurrences=min_occurrences,
            )
        
        # Detect pattern type and interval_days based on distribution
        pattern_type = None
        frequency = None
        interval_days = None
        
        if distribution == "perfect_monthly" or distribution == "monthly_with_gaps":
            pattern_type = "MONTHLY"
            frequency = "monthly"
            interval_days = 30  # Default monthly
            reasoning = f"Monthly pattern detected with {total_periods} periods"
        
        elif distribution == "bi_monthly":
            pattern_type = "MONTHLY"  # Biweekly could be weekly, use BIWEEKLY if available
            frequency = "bi-monthly"
            interval_days = 60  # ~2 months
            reasoning = "Bi-monthly pattern detected (intervals of ~2 months)"
        
        elif distribution == "quarterly":
            pattern_type = "QUARTERLY"
            frequency = "quarterly"
            interval_days = 90
            reasoning = "Quarterly pattern detected (intervals of ~3 months)"
        
        elif distribution == "irregular_intervals":
            # Check if it's still recurring despite irregular gaps
            if consecutive_periods >= min_occurrences:
                pattern_type = "MONTHLY"
                frequency = "monthly"
                interval_days = 30
                reasoning = f"Flexible monthly pattern with {consecutive_periods} consecutive occurrences"
            else:
                return PatternDetectionResult(
                    is_recurring=False,
                    reasoning="Irregular intervals with insufficient consecutive occurrences",
                    actual_occurrences=total_periods,
                    required_occurrences=min_occurrences,
                )
        
        else:  # insufficient_data or other
            return PatternDetectionResult(
                is_recurring=False,
                reasoning=f"Unable to detect pattern: {distribution}",
                actual_occurrences=total_periods,
                required_occurrences=min_occurrences,
            )
        
        # If we got here, we have a pattern
        result = PatternDetectionResult(
            is_recurring=True,
            pattern_type=pattern_type,
            frequency=frequency,
            reasoning=reasoning,
            actual_occurrences=total_periods,
            required_occurrences=min_occurrences,
        )
        
        # Store interval_days for DB persistence
        result.interval_days = interval_days
        
        logger.info(f"Pattern detected: {result.pattern_type} with interval {interval_days} days")
        
        return result
    
    def analyze_monthly_consistency(self, buckets: dict) -> dict:
        """
        Analyze month-to-month consistency.
        
        Returns metrics like:
        - Same day of month?
        - Date variance
        - Day-of-week pattern?
        """
        bucket_list = buckets.get("buckets", [])
        
        if not bucket_list:
            return {"analysis": "no_data"}
        
        # Extract dates from all periods
        all_dates = []
        for bucket in bucket_list:
            for date_str in bucket.get("dates", []):
                all_dates.append(date_str)
        
        if not all_dates:
            return {"analysis": "no_date_data"}
        
        return {
            "total_transactions": len(all_dates),
            "date_distribution": "analyzed",
            "periods_covered": len(bucket_list),
        }
