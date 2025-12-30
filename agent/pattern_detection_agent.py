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
    pattern_type: Optional[str] = None  # "fixed_monthly", "variable_monthly", etc.
    frequency: Optional[str] = None  # "monthly", "bi-monthly", "quarterly"
    reasoning: str = ""
    required_occurrences: int = 3  # Minimum transactions needed
    actual_occurrences: int = 0  # Actual recurring transactions found
    
    def to_dict(self):
        return {
            "is_recurring": self.is_recurring,
            "pattern_type": self.pattern_type,
            "frequency": self.frequency,
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
        
        Args:
            bucket_analysis: Output from PeriodBucketingAgent.analyze_bucket_distribution()
            min_occurrences: Minimum occurrences required for recurring pattern
        
        Returns:
            PatternDetectionResult
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
        
        # Detect pattern type based on distribution
        pattern_type = None
        frequency = None
        
        if distribution == "perfect_monthly":
            pattern_type = "fixed_monthly" if consecutive_periods >= min_occurrences else "variable_monthly"
            frequency = "monthly"
            reasoning = f"Perfect monthly pattern with {consecutive_periods} consecutive periods"
        
        elif distribution == "monthly_with_gaps":
            pattern_type = "flexible_monthly"
            frequency = "monthly"
            reasoning = f"Monthly pattern detected with {total_periods} periods and {len(bucket_analysis.get('gaps', []))} gaps"
        
        elif distribution == "bi_monthly":
            pattern_type = "variable_monthly"
            frequency = "bi-monthly"
            reasoning = "Bi-monthly pattern detected (gaps of 2 months)"
        
        elif distribution == "quarterly":
            pattern_type = "variable_monthly"
            frequency = "quarterly"
            reasoning = "Quarterly pattern detected (gaps of 3 months)"
        
        elif distribution == "irregular_intervals":
            # Check if it's still recurring despite irregular gaps
            if consecutive_periods >= min_occurrences:
                pattern_type = "flexible_monthly"
                frequency = "monthly"
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
        
        logger.info(f"Pattern detected: {result.pattern_type} with frequency {result.frequency}")
        
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
