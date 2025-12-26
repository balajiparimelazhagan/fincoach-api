"""
Period Bucketing Agent for grouping transactions by time periods.
Part of the Spending Analysis agentic system using Google ADK.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
from decimal import Decimal
import logging
from collections import defaultdict

from google.adk.agents.llm_agent import Agent

logger = logging.getLogger(__name__)


@dataclass
class PeriodBucket:
    """Represents aggregated transactions in a time period"""
    period: str  # Format: "2025-01" for monthly, "2025-W01" for weekly, etc.
    year: int
    month: int
    transaction_dates: List[datetime] = field(default_factory=list)
    amounts: List[Decimal] = field(default_factory=list)
    transaction_count: int = 0
    total_amount: Decimal = Decimal("0")
    avg_amount: Decimal = Decimal("0")
    min_amount: Decimal = Decimal("0")
    max_amount: Decimal = Decimal("0")
    
    def finalize(self):
        """Finalize aggregates after adding all transactions"""
        if self.amounts:
            self.transaction_count = len(self.amounts)
            self.total_amount = sum(self.amounts)
            self.avg_amount = self.total_amount / self.transaction_count
            self.min_amount = min(self.amounts)
            self.max_amount = max(self.amounts)
    
    def to_dict(self):
        return {
            "period": self.period,
            "year": self.year,
            "month": self.month,
            "transaction_count": self.transaction_count,
            "total_amount": float(self.total_amount),
            "avg_amount": float(self.avg_amount),
            "min_amount": float(self.min_amount),
            "max_amount": float(self.max_amount),
            "dates": [d.isoformat() for d in self.transaction_dates],
        }


@dataclass
class TransactorBuckets:
    """Buckets for a single transactor"""
    transactor_id: str
    transactor_name: str
    buckets: Dict[str, PeriodBucket] = field(default_factory=dict)
    
    def add_transaction(self, date: datetime, amount: Decimal):
        """Add a transaction to the appropriate bucket"""
        period = f"{date.year}-{date.month:02d}"
        year = date.year
        month = date.month
        
        if period not in self.buckets:
            self.buckets[period] = PeriodBucket(
                period=period,
                year=year,
                month=month
            )
        
        bucket = self.buckets[period]
        bucket.transaction_dates.append(date)
        bucket.amounts.append(amount)
    
    def finalize(self):
        """Finalize all buckets"""
        for bucket in self.buckets.values():
            bucket.finalize()
    
    def get_sorted_buckets(self) -> List[PeriodBucket]:
        """Get buckets sorted by period (oldest first)"""
        return sorted(self.buckets.values(), key=lambda b: b.period)


class PeriodBucketingAgent:
    """
    Agent for grouping transactions by time periods.
    
    Responsibilities:
    1. Group transactions by month (or custom period)
    2. Aggregate amounts per period
    3. Calculate period-level statistics
    4. Prepare data for pattern detection
    """
    
    def __init__(self):
        """Initialize the period bucketing agent"""
        self.agent = Agent(
            model="gemini-2.5-flash",
            name="period_bucketing_agent",
            description="Groups and aggregates transactions by time periods for pattern analysis",
            instruction=self._get_system_instruction(),
        )
        logger.info("Period Bucketing Agent initialized")
    
    def _get_system_instruction(self) -> str:
        """Get system instruction for period bucketing"""
        return """You are an expert at analyzing transaction time periods for pattern detection.

Your task is to help analyze how transactions are distributed across time periods.

For a given set of transactions from a single transactor:
1. Identify the time periods (months) in which transactions occur
2. Count transactions in each period
3. Calculate aggregate amounts per period
4. Identify period gaps (months without transactions)
5. Detect which periods have consecutive presence

Key Outputs:
- Which months have transactions from this transactor
- Which months are missing transactions
- Which periods show consecutive presence
- Summary statistics per period

You should be able to answer questions like:
- "In which 3 consecutive months does this transactor appear?"
- "What are the gaps between transactions?"
- "Is there a monthly pattern?"
- "Are transactions bi-monthly or quarterly?"

Respond with analysis of the transaction timeline."""

    def bucket_transactions(self, transactions_data: Dict) -> TransactorBuckets:
        """
        Bucket transactions for a single transactor by month.
        
        Args:
            transactions_data: Dict with:
                - transactor_id: UUID
                - transactor_name: str
                - transactions: List[{date: datetime, amount: Decimal}]
        
        Returns:
            TransactorBuckets with organized data
        """
        transactor_id = transactions_data.get("transactor_id")
        transactor_name = transactions_data.get("transactor_name")
        transactions = transactions_data.get("transactions", [])
        
        logger.info(f"Bucketing {len(transactions)} transactions for transactor {transactor_id}")
        
        result = TransactorBuckets(
            transactor_id=transactor_id,
            transactor_name=transactor_name
        )
        
        # Sort transactions by date
        sorted_txns = sorted(transactions, key=lambda t: t.get("date"))
        
        # Add each transaction to appropriate bucket
        for txn in sorted_txns:
            date = txn.get("date")
            amount = Decimal(str(txn.get("amount", 0)))
            
            if date:
                result.add_transaction(date, amount)
        
        # Finalize all buckets
        result.finalize()
        
        logger.info(f"Created {len(result.buckets)} buckets for transactor {transactor_id}")
        
        return result
    
    def analyze_bucket_distribution(self, buckets: TransactorBuckets) -> Dict:
        """
        Analyze the distribution of buckets (periods).
        
        Returns analysis like:
        - Number of buckets (periods with transactions)
        - Consecutive period count
        - Period gaps
        - Distribution summary
        """
        sorted_buckets = buckets.get_sorted_buckets()
        
        if not sorted_buckets:
            return {
                "total_periods": 0,
                "consecutive_periods": 0,
                "gaps": [],
                "distribution": "no_data"
            }
        
        # Analyze consecutive periods
        consecutive_count = self._find_max_consecutive_periods(sorted_buckets)
        
        # Find gaps between periods
        gaps = self._find_period_gaps(sorted_buckets)
        
        analysis = {
            "total_periods": len(sorted_buckets),
            "consecutive_periods": consecutive_count,
            "max_gap_months": max([g["gap_months"] for g in gaps], default=0),
            "gaps": gaps,
            "distribution": self._classify_distribution(sorted_buckets),
            "buckets": [b.to_dict() for b in sorted_buckets],
        }
        
        logger.info(f"Bucket analysis for {buckets.transactor_id}: {consecutive_count} consecutive periods")
        
        return analysis
    
    def _find_max_consecutive_periods(self, sorted_buckets: List[PeriodBucket]) -> int:
        """Find the longest run of consecutive months with transactions"""
        if not sorted_buckets:
            return 0
        
        max_consecutive = 1
        current_consecutive = 1
        
        for i in range(1, len(sorted_buckets)):
            prev_period = sorted_buckets[i-1].period  # "2025-01"
            curr_period = sorted_buckets[i].period    # "2025-02"
            
            prev_year, prev_month = map(int, prev_period.split('-'))
            curr_year, curr_month = map(int, curr_period.split('-'))
            
            # Check if consecutive month
            expected_next_month = (prev_month + 1) if prev_month < 12 else 1
            expected_next_year = prev_year if prev_month < 12 else prev_year + 1
            
            if curr_year == expected_next_year and curr_month == expected_next_month:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 1
        
        return max_consecutive
    
    def _find_period_gaps(self, sorted_buckets: List[PeriodBucket]) -> List[Dict]:
        """Find gaps (missing months) between transactions"""
        gaps = []
        
        for i in range(len(sorted_buckets) - 1):
            prev_period = sorted_buckets[i].period
            curr_period = sorted_buckets[i+1].period
            
            prev_year, prev_month = map(int, prev_period.split('-'))
            curr_year, curr_month = map(int, curr_period.split('-'))
            
            # Calculate months between
            months_between = (curr_year - prev_year) * 12 + (curr_month - prev_month) - 1
            
            if months_between > 0:
                gaps.append({
                    "from_period": prev_period,
                    "to_period": curr_period,
                    "gap_months": months_between,
                })
        
        return gaps
    
    def _classify_distribution(self, sorted_buckets: List[PeriodBucket]) -> str:
        """Classify the distribution pattern"""
        if len(sorted_buckets) < 2:
            return "insufficient_data"
        
        # Check for perfect monthly (every month)
        max_consecutive = self._find_max_consecutive_periods(sorted_buckets)
        gaps = self._find_period_gaps(sorted_buckets)
        
        if len(gaps) == 0:
            return "perfect_monthly"
        elif all(g["gap_months"] == 1 for g in gaps):
            return "monthly_with_gaps"
        elif all(g["gap_months"] == 2 for g in gaps):
            return "bi_monthly"
        elif all(g["gap_months"] == 3 for g in gaps):
            return "quarterly"
        else:
            return "irregular_intervals"
