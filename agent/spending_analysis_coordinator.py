"""
Spending Analysis Coordinator using Agent-to-Agent Communication.
Orchestrates recurring pattern detection for transaction analysis.
Follows the same A2A pattern as EmailProcessingCoordinator.
"""

from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime
from decimal import Decimal
import logging

from .period_bucketing_agent import PeriodBucketingAgent
from .pattern_detection_agent import PatternDetectionAgent
from .amount_analysis_agent import AmountAnalysisAgent
from .confidence_calculator import ConfidenceCalculator

logger = logging.getLogger(__name__)


@dataclass
class PatternAnalysisResult:
    """Result of pattern analysis for a single transactor"""
    transactor_id: str
    transactor_name: str
    pattern_detected: bool
    pattern_type: Optional[str] = None
    frequency: Optional[str] = None
    interval_days: Optional[int] = None  # Numeric interval in days
    amount_behavior: Optional[str] = None  # FIXED, VARIABLE, HIGHLY_VARIABLE
    direction: Optional[str] = None  # DEBIT, CREDIT
    confidence: float = 0.0
    avg_amount: Optional[Decimal] = None
    min_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None
    amount_variance: float = 0.0
    total_occurrences: int = 0
    outliers_excluded: int = 0
    reasoning: str = ""
    first_transaction_date: Optional[datetime] = None
    last_transaction_date: Optional[datetime] = None
    analyzed_at: datetime = None
    
    def to_dict(self):
        return {
            "transactor_id": str(self.transactor_id),
            "transactor_name": self.transactor_name,
            "pattern_detected": self.pattern_detected,
            "pattern_type": self.pattern_type,
            "frequency": self.frequency,
            "interval_days": self.interval_days,
            "amount_behavior": self.amount_behavior,
            "direction": self.direction,
            "confidence": round(self.confidence, 3),
            "avg_amount": float(self.avg_amount) if self.avg_amount else None,
            "min_amount": float(self.min_amount) if self.min_amount else None,
            "max_amount": float(self.max_amount) if self.max_amount else None,
            "amount_variance": round(self.amount_variance, 1),
            "total_occurrences": self.total_occurrences,
            "outliers_excluded": self.outliers_excluded,
            "reasoning": self.reasoning,
        }


@dataclass
class SpendingAnalysisResult:
    """Result of overall spending analysis job"""
    user_id: str
    job_id: str
    patterns_found: List[PatternAnalysisResult]
    total_transactors_analyzed: int
    patterns_detected_count: int
    job_duration_seconds: float = 0.0
    error_messages: List[str] = None
    success: bool = True
    
    def __post_init__(self):
        if self.error_messages is None:
            self.error_messages = []
    
    def to_dict(self):
        return {
            "user_id": str(self.user_id),
            "job_id": str(self.job_id),
            "total_transactors_analyzed": self.total_transactors_analyzed,
            "patterns_detected_count": self.patterns_detected_count,
            "job_duration_seconds": round(self.job_duration_seconds, 2),
            "patterns": [p.to_dict() for p in self.patterns_found],
            "errors": self.error_messages,
            "success": self.success,
        }


class SpendingAnalysisCoordinator:
    """
    Coordinator implementing Agent-to-Agent (A2A) communication for spending analysis.
    
    Architecture:
    1. Period Bucketing Agent - Groups transactions by time periods
    2. Pattern Detection Agent - Identifies recurring patterns
    3. Amount Analysis Agent - Analyzes amounts and detects outliers
    4. Confidence Calculator - Computes overall confidence
    
    Communication Flow:
    PeriodBucketing -> PatternDetection -> AmountAnalysis -> ConfidenceCalculation
    
    This ensures:
    - Transactions are properly aggregated before analysis
    - Patterns are validated before amount analysis
    - Outliers are excluded from confidence calculations
    - Each signal contributes to final confidence score
    """
    
    def __init__(self):
        """Initialize the spending analysis coordinator with all agents"""
        logger.info("Initializing Spending Analysis Coordinator with A2A communication")
        
        self.period_bucketing_agent = PeriodBucketingAgent()
        self.pattern_detection_agent = PatternDetectionAgent()
        self.amount_analysis_agent = AmountAnalysisAgent()
        self.confidence_calculator = ConfidenceCalculator()
        
        logger.info("All agents initialized successfully")
    
    def analyze_transactor_patterns(
        self,
        transactor_id: str,
        transactor_name: str,
        direction: str,
        transactions: List[dict],
        min_occurrences: int = 3,
    ) -> PatternAnalysisResult:
        """
        Analyze patterns for a single transactor using A2A coordination.
        
        Step 1: Period Bucketing (Agent 1)
        Step 2: Pattern Detection (Agent 2)
        Step 3: Amount Analysis (Agent 3)
        Step 4: Confidence Calculation (Agent 4)
        
        Args:
            transactor_id: UUID of transactor
            transactor_name: Name of transactor
            direction: DEBIT or CREDIT (from transaction type)
            transactions: List of {date, amount} dicts
            min_occurrences: Minimum periods needed for recurring pattern
        
        Returns:
            PatternAnalysisResult with detailed analysis
        """
        logger.info(f"[A2A] Analyzing patterns for transactor: {transactor_name}, direction: {direction}")
        
        try:
            # STEP 1: Agent 1 - Period Bucketing
            logger.info(f"[A2A] Step 1: Period Bucketing Agent processing {len(transactions)} transactions")
            
            transactions_data = {
                "transactor_id": transactor_id,
                "transactor_name": transactor_name,
                "transactions": transactions,
            }
            
            transactor_buckets = self.period_bucketing_agent.bucket_transactions(transactions_data)
            bucket_analysis = self.period_bucketing_agent.analyze_bucket_distribution(transactor_buckets)
            
            logger.info(
                f"[A2A] Step 1 Complete: {len(transactor_buckets.buckets)} periods identified, "
                f"{bucket_analysis.get('consecutive_periods')} consecutive"
            )
            
            # STEP 2: Agent 2 - Pattern Detection
            logger.info(f"[A2A] Step 2: Pattern Detection Agent analyzing bucket distribution")
            
            pattern_result = self.pattern_detection_agent.detect_pattern(
                bucket_analysis,
                min_occurrences=min_occurrences,
            )
            
            logger.info(
                f"[A2A] Step 2 Complete: Pattern detected={pattern_result.is_recurring}, "
                f"type={pattern_result.pattern_type}, frequency={pattern_result.frequency}"
            )
            
            # If no pattern detected, return early
            if not pattern_result.is_recurring:
                logger.info(f"[A2A] No recurring pattern found: {pattern_result.reasoning}")
                now = datetime.utcnow()
                return PatternAnalysisResult(
                    transactor_id=transactor_id,
                    transactor_name=transactor_name,
                    pattern_detected=False,
                    reasoning=pattern_result.reasoning,
                    total_occurrences=pattern_result.actual_occurrences,
                    first_transaction_date=min((t['date'] for t in transactions), default=None),
                    last_transaction_date=max((t['date'] for t in transactions), default=None),
                    analyzed_at=now,
                )

            # STEP 3: Agent 3 - Amount Analysis (with outlier detection)
            logger.info(f"[A2A] Step 3: Amount Analysis Agent detecting outliers")

            amounts = [Decimal(str(t["amount"])) for t in transactions]
            amount_analysis = self.amount_analysis_agent.analyze_amounts(
                amounts,
                transactor_name=transactor_name,
                bucket_info=bucket_analysis,
            )

            logger.info(
                f"[A2A] Step 3 Complete: {len(amount_analysis.outliers_detected)} outliers excluded, "
                f"variance={amount_analysis.variance_percent:.1f}%, "
                f"type={'fixed' if amount_analysis.is_fixed_amount else 'variable'}"
            )

            # STEP 4: Agent 4 - Confidence Calculator
            logger.info(f"[A2A] Step 4: Confidence Calculator computing overall score")

            pattern_analysis = {
                "pattern_type": pattern_result.pattern_type,
                "frequency": pattern_result.frequency,
                "bucket_analysis": bucket_analysis,
                "amount_analysis": amount_analysis.to_dict(),
            }

            confidence_scores = self.confidence_calculator.calculate_confidence(pattern_analysis)

            logger.info(
                f"[A2A] Step 4 Complete: Overall confidence={confidence_scores.overall_confidence:.3f}"
            )

            # FINAL: Compile result
            logger.info(
                f"[A2A] Analysis Complete for {transactor_name}: "
                f"{pattern_result.pattern_type} with {confidence_scores.overall_confidence:.3f} confidence"
            )

            first_date = min((t['date'] for t in transactions), default=None)
            last_date = max((t['date'] for t in transactions), default=None)
            now = datetime.utcnow()
            
            # Determine amount_behavior from analysis
            amount_behavior = "FIXED"
            if amount_analysis.is_highly_variable:
                amount_behavior = "HIGHLY_VARIABLE"
            elif amount_analysis.is_variable_amount:
                amount_behavior = "VARIABLE"
            
            return PatternAnalysisResult(
                transactor_id=transactor_id,
                transactor_name=transactor_name,
                pattern_detected=True,
                pattern_type=pattern_result.pattern_type,
                frequency=pattern_result.frequency,
                interval_days=pattern_result.interval_days,
                amount_behavior=amount_behavior,
                direction=direction,  # From parameter
                confidence=confidence_scores.overall_confidence,
                avg_amount=amount_analysis.avg_amount,
                min_amount=amount_analysis.min_amount,
                max_amount=amount_analysis.max_amount,
                amount_variance=amount_analysis.variance_percent,
                total_occurrences=pattern_result.actual_occurrences,
                outliers_excluded=len(amount_analysis.outliers_detected),
                reasoning=f"{pattern_result.reasoning} | {amount_analysis.reasoning}",
                first_transaction_date=first_date,
                last_transaction_date=last_date,
                analyzed_at=now,
            )
            
        except Exception as e:
            logger.error(
                f"[A2A] Error analyzing patterns for {transactor_name}: {str(e)}",
                exc_info=True
            )
            return PatternAnalysisResult(
                transactor_id=transactor_id,
                transactor_name=transactor_name,
                pattern_detected=False,
                reasoning=f"Error during analysis: {str(e)}",
            )
    
