"""
Confidence Calculator for computing overall pattern confidence.
"""

from dataclasses import dataclass
from typing import Dict
import logging

logger = logging.getLogger(__name__)


@dataclass
class ConfidenceScores:
    """Individual confidence signals"""
    frequency_consistency: float  # 0-1: How consistent is the frequency?
    amount_consistency: float  # 0-1: How consistent are the amounts?
    date_consistency: float  # 0-1: How consistent are the dates within period?
    data_points: float  # 0-1: How many data points do we have?
    overall_confidence: float  # 0-1: Combined confidence
    
    def to_dict(self):
        return {
            "frequency_consistency": round(self.frequency_consistency, 3),
            "amount_consistency": round(self.amount_consistency, 3),
            "date_consistency": round(self.date_consistency, 3),
            "data_points": round(self.data_points, 3),
            "overall_confidence": round(self.overall_confidence, 3),
        }


class ConfidenceCalculator:
    """
    Calculator for determining pattern confidence.

    Combines multiple signals using a weighted average:
    - Frequency consistency (35%)
    - Amount consistency (25%)
    - Date consistency (20%)
    - Data points count (15%)
    - Pattern type strength (5%)
    """

    def __init__(self):
        logger.info("Confidence Calculator initialized")

    def calculate_confidence(
        self,
        pattern_analysis: Dict,
    ) -> ConfidenceScores:
        """
        Calculate confidence score for a pattern.
        
        Args:
            pattern_analysis: Dict containing:
                - pattern_type: str
                - frequency: str
                - bucket_analysis: dict (from PeriodBucketingAgent)
                - amount_analysis: dict (from AmountAnalysisAgent)
        
        Returns:
            ConfidenceScores with individual and overall scores
        """
        pattern_type = pattern_analysis.get("pattern_type", "unknown")
        frequency = pattern_analysis.get("frequency", "unknown")
        bucket_analysis = pattern_analysis.get("bucket_analysis", {})
        amount_analysis = pattern_analysis.get("amount_analysis", {})
        
        logger.info(f"Calculating confidence for {pattern_type} pattern")
        
        # Calculate individual scores
        frequency_score = self._score_frequency_consistency(frequency, bucket_analysis)
        amount_score = self._score_amount_consistency(amount_analysis)
        date_score = self._score_date_consistency(bucket_analysis)
        data_score = self._score_data_points(bucket_analysis)
        
        # Calculate overall using weighted average
        # Weights: frequency=35%, amount=25%, dates=20%, data_points=15%, pattern=5%
        pattern_strength = self._get_pattern_strength(pattern_type)
        
        overall = (
            (frequency_score * 0.35) +
            (amount_score * 0.25) +
            (date_score * 0.20) +
            (data_score * 0.15) +
            (pattern_strength * 0.05)
        )
        
        # Clamp to [0, 1]
        overall = max(0.0, min(1.0, overall))
        
        result = ConfidenceScores(
            frequency_consistency=frequency_score,
            amount_consistency=amount_score,
            date_consistency=date_score,
            data_points=data_score,
            overall_confidence=overall,
        )
        
        logger.info(
            f"Confidence scores: frequency={frequency_score:.2f}, "
            f"amount={amount_score:.2f}, dates={date_score:.2f}, "
            f"data={data_score:.2f}, overall={overall:.2f}"
        )
        
        return result
    
    def _score_frequency_consistency(self, frequency: str, bucket_analysis: dict) -> float:
        """Score frequency consistency"""
        distribution = bucket_analysis.get("distribution", "")
        gaps = bucket_analysis.get("gaps", [])
        
        if distribution == "perfect_monthly":
            return 0.95
        elif distribution == "monthly_with_gaps":
            # Fewer gaps = higher score
            gap_count = len(gaps)
            if gap_count <= 1:
                return 0.85
            elif gap_count <= 2:
                return 0.75
            else:
                return 0.65
        elif distribution == "bi_monthly":
            return 0.90
        elif distribution == "quarterly":
            return 0.85
        elif distribution == "irregular_intervals":
            return 0.50
        else:
            return 0.30
    
    def _score_amount_consistency(self, amount_analysis: dict) -> float:
        """Score amount consistency"""
        if not amount_analysis:
            return 0.5
        
        is_fixed = amount_analysis.get("is_fixed_amount", False)
        is_variable = amount_analysis.get("is_variable_amount", False)
        is_highly_variable = amount_analysis.get("is_highly_variable", False)
        variance = amount_analysis.get("variance_percent", 50)
        
        if is_fixed:
            return 0.95
        elif is_variable:
            # Score inversely with variance
            # 5% variance = 0.85, 50% variance = 0.45
            return max(0.45, 0.95 - (variance - 5) * 0.01)
        elif is_highly_variable:
            return 0.30
        else:
            return 0.50
    
    def _score_date_consistency(self, bucket_analysis: dict) -> float:
        """Score date consistency (same date each period)"""
        # This is simplified - in full implementation would track actual dates
        # For now, we'll use a default moderate score
        # Full implementation would check bucket.avg_day_of_period variance
        
        buckets = bucket_analysis.get("buckets", [])
        if not buckets:
            return 0.5
        
        # Simplified: assume moderate date consistency by default
        # Full implementation would calculate actual day-of-month variance
        return 0.70
    
    def _score_data_points(self, bucket_analysis: dict) -> float:
        """Score confidence based on number of data points"""
        total_periods = bucket_analysis.get("total_periods", 0)
        
        if total_periods >= 10:
            return 0.95
        elif total_periods >= 6:
            return 0.85
        elif total_periods >= 5:
            return 0.75
        elif total_periods >= 4:
            return 0.70
        elif total_periods >= 3:
            return 0.60
        else:
            return 0.30
    
    def calculate_final_confidence(
        self,
        base_confidence: float,
        confidence_multiplier: float = 1.0
    ) -> float:
        """
        Apply streak multiplier to base confidence.
        
        impl_2.md formula:
        final_confidence = base_confidence * confidence_multiplier
        
        Args:
            base_confidence: Score from calculate_confidence (0-1)
            confidence_multiplier: Streak health multiplier (0-1)
        
        Returns:
            Final confidence score (0-1), clamped
        """
        final = base_confidence * confidence_multiplier
        # Clamp to [0, 1]
        return max(0.0, min(1.0, final))
    
    def _get_pattern_strength(self, pattern_type: str) -> float:
        """Get inherent strength of pattern type"""
        pattern_strengths = {
            "fixed_monthly": 0.95,
            "variable_monthly": 0.75,
            "flexible_monthly": 0.60,
            "bi_monthly": 0.80,
            "quarterly": 0.70,
            "custom_interval": 0.75,
            "multi_monthly": 0.50,
        }
        
        return pattern_strengths.get(pattern_type, 0.50)
