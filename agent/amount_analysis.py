"""
Amount Analysis Agent for analyzing transaction amounts and detecting outliers.
Part of the Spending Analysis agentic system.
"""

from dataclasses import dataclass
from typing import List, Optional, Dict
from decimal import Decimal
import statistics
import logging

logger = logging.getLogger(__name__)


@dataclass
class AmountAnalysisResult:
    """Result of amount analysis"""
    avg_amount: Decimal
    min_amount: Decimal
    max_amount: Decimal
    variance_percent: float
    is_fixed_amount: bool  # <5% variance = fixed
    is_variable_amount: bool  # 5-50% variance
    is_highly_variable: bool  # >50% variance
    outliers_detected: List[Decimal]  # Detected and excluded outliers
    outlier_reasons: Dict[str, str]  # Reason for excluding each outlier
    used_amounts: List[Decimal]  # Amounts used for calculation (after outlier removal)
    reasoning: str = ""
    
    def to_dict(self):
        return {
            "avg_amount": float(self.avg_amount),
            "min_amount": float(self.min_amount),
            "max_amount": float(self.max_amount),
            "variance_percent": self.variance_percent,
            "is_fixed_amount": self.is_fixed_amount,
            "is_variable_amount": self.is_variable_amount,
            "is_highly_variable": self.is_highly_variable,
            "outliers_detected": [float(o) for o in self.outliers_detected],
            "outlier_reasons": self.outlier_reasons,
            "used_amounts_count": len(self.used_amounts),
            "reasoning": self.reasoning,
        }


class AmountAnalysisAgent:
    """
    Agent for analyzing transaction amounts and detecting outliers.

    Uses IQR statistical method for deterministic outlier detection,
    then classifies amounts as fixed, variable, or highly variable.
    """
    
    def __init__(self):
        logger.info("Amount Analysis Agent initialized")

    def analyze_amounts(
        self,
        amounts: List[Decimal],
        transactor_name: str = "",
        bucket_info: Optional[dict] = None,
    ) -> AmountAnalysisResult:
        """
        Analyze transaction amounts for patterns and outliers.
        
        Args:
            amounts: List of transaction amounts
            transactor_name: Name of transactor (for context)
            bucket_info: Optional bucket distribution info for context
        
        Returns:
            AmountAnalysisResult with analysis and outlier detection
        """
        if not amounts:
            logger.warning("No amounts to analyze")
            return AmountAnalysisResult(
                avg_amount=Decimal("0"),
                min_amount=Decimal("0"),
                max_amount=Decimal("0"),
                variance_percent=0.0,
                is_fixed_amount=False,
                is_variable_amount=False,
                is_highly_variable=False,
                outliers_detected=[],
                outlier_reasons={},
                used_amounts=[],
                reasoning="No amounts to analyze",
            )
        
        logger.info(f"Analyzing {len(amounts)} amounts for {transactor_name}")

        # Use IQR statistical method for deterministic outlier detection
        outliers_result = self._detect_outliers_statistical(amounts)
        outliers = outliers_result.get("outliers", [])
        outlier_reasons = {str(o["amount"]): o["reason"] for o in outliers}
        
        # Create set of outlier amounts for filtering
        outlier_amounts = {Decimal(str(o["amount"])) for o in outliers}
        
        # Filter out outliers
        used_amounts = [a for a in amounts if a not in outlier_amounts]
        
        if not used_amounts:
            # All were outliers, use original
            logger.warning(f"All amounts were detected as outliers, using original")
            used_amounts = amounts
            outliers = []
            outlier_reasons = {}
        
        logger.info(f"Using {len(used_amounts)} amounts after removing {len(outliers)} outliers")
        
        # Calculate statistics on filtered amounts
        avg = sum(used_amounts) / len(used_amounts)
        min_amt = min(used_amounts)
        max_amt = max(used_amounts)
        
        # Calculate variance
        variance_percent = self._calculate_variance_percent(used_amounts, avg)
        
        # Classify amount pattern
        is_fixed = variance_percent < 5
        is_variable = 5 <= variance_percent <= 50
        is_highly_variable = variance_percent > 50
        
        result = AmountAnalysisResult(
            avg_amount=avg,
            min_amount=min_amt,
            max_amount=max_amt,
            variance_percent=variance_percent,
            is_fixed_amount=is_fixed,
            is_variable_amount=is_variable,
            is_highly_variable=is_highly_variable,
            outliers_detected=[Decimal(str(o["amount"])) for o in outliers],
            outlier_reasons=outlier_reasons,
            used_amounts=used_amounts,
            reasoning=outliers_result.get("reasoning", ""),
        )
        
        logger.info(
            f"Amount analysis: avg={avg}, variance={variance_percent:.1f}%, "
            f"fixed={is_fixed}, variable={is_variable}, highly_variable={is_highly_variable}"
        )
        
        return result
    
    def _detect_outliers_statistical(self, amounts: List[Decimal]) -> dict:
        """Statistical fallback for outlier detection using IQR method"""
        if len(amounts) < 4:
            return {"outliers": [], "reasoning": "Too few amounts for statistical outlier detection"}
        
        sorted_amounts = sorted(amounts)
        n = len(sorted_amounts)
        
        # Calculate Q1, Q3
        q1_idx = n // 4
        q3_idx = 3 * n // 4
        q1 = sorted_amounts[q1_idx]
        q3 = sorted_amounts[q3_idx]
        iqr = q3 - q1
        
        # IQR method: outliers are outside [Q1 - 1.5*IQR, Q3 + 1.5*IQR]
        factor = Decimal('1.5')
        lower_bound = q1 - factor * iqr
        upper_bound = q3 + factor * iqr
        
        outliers = []
        for amt in amounts:
            if amt < lower_bound or amt > upper_bound:
                outliers.append({
                    "amount": float(amt),
                    "reason": f"Outside IQR bounds [{float(lower_bound):.2f}, {float(upper_bound):.2f}]"
                })
        
        reasoning = f"Statistical IQR method: {len(outliers)} outliers detected from {len(amounts)} amounts"
        
        return {
            "outliers": outliers,
            "reasoning": reasoning,
            "should_exclude": len(outliers) > 0,
        }
    
    def _calculate_variance_percent(self, amounts: List[Decimal], mean: Decimal) -> float:
        """Calculate coefficient of variation"""
        if not amounts or mean == 0:
            return 0.0
        
        # Standard deviation
        squared_diffs = [(a - mean) ** 2 for a in amounts]
        variance = sum(squared_diffs) / len(amounts)
        std_dev = variance ** Decimal('0.5')
        
        # Coefficient of variation as percentage
        cv = (std_dev / mean) * 100
        
        return float(cv)
