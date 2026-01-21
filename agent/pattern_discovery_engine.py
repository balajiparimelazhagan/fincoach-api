"""
Deterministic Pattern Discovery Engine

Implements the exact step-by-step algorithm for discovering recurring patterns
with NO ML, NO LLM assumptions, and NO calendar-month dependencies.

Steps 0-9: Pattern Discovery
Steps 10-15: Obligation Computation (in separate module)
"""
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from decimal import Decimal
import math
import statistics
from dataclasses import dataclass

from app.logging_config import get_logger

logger = get_logger(__name__)
from enum import Enum


class PatternCase(Enum):
    """Deterministic pattern case classifications"""
    FIXED_MONTHLY = "FIXED_MONTHLY"              # ~30 days, low CV
    VARIABLE_MONTHLY = "VARIABLE_MONTHLY"        # ~30 days, moderate CV
    FLEXIBLE_MONTHLY = "FLEXIBLE_MONTHLY"        # Irregular timing, but present each month
    BI_MONTHLY = "BI_MONTHLY"                    # ~60 days
    QUARTERLY = "QUARTERLY"                      # ~90 days
    CUSTOM_INTERVAL = "CUSTOM_INTERVAL"          # Other stable intervals
    FREQUENT_VARIABLE = "FREQUENT_VARIABLE"      # Noise (groceries, etc.)


class AmountBehaviorType(Enum):
    """Amount behavior classifications"""
    FIXED = "FIXED"                    # CV < 0.05
    VARIABLE = "VARIABLE"              # CV < 0.30
    HIGHLY_VARIABLE = "HIGHLY_VARIABLE"  # CV >= 0.30


@dataclass
class Transaction:
    """Minimal transaction representation for pattern discovery"""
    txn_id: str
    txn_date: datetime
    amount: Decimal


@dataclass
class AmountCluster:
    """Represents a group of transactions with similar amounts"""
    transactions: List[Transaction]
    min_amount: Decimal
    max_amount: Decimal
    avg_amount: Decimal
    cv: float  # coefficient of variation


@dataclass
class PatternCandidate:
    """A candidate recurring pattern discovered from data"""
    cluster: AmountCluster
    pattern_case: PatternCase
    amount_behavior: AmountBehaviorType
    interval_days: Optional[int]
    avg_gap_days: float
    stddev_gap_days: float
    confidence: float
    transactions: List[Transaction]


class DeterministicPatternDiscovery:
    """
    Deterministic pattern discovery engine.
    No ML, no LLM, no guessing.
    """
    
    # Configuration constants (from requirements)
    MIN_TRANSACTIONS_REQUIRED = 1
    FREQUENT_THRESHOLD_PER_30_DAYS = 3
    AMOUNT_TOLERANCE_PERCENT = 0.25  # 25%
    AMOUNT_TOLERANCE_ABSOLUTE = Decimal('50.00')  # ₹50
    MIN_INTERVAL_DAYS = 10
    
    # Case classification ranges
    MONTHLY_RANGE = (27, 33)
    BI_MONTHLY_RANGE = (55, 65)
    QUARTERLY_RANGE = (85, 95)
    
    # Amount behavior thresholds
    CV_FIXED_THRESHOLD = 0.05
    CV_VARIABLE_THRESHOLD = 0.30
    
    def __init__(self, transactions: List[Transaction]):
        """
        Initialize with a list of transactions for one (user_id, transactor_id, direction, currency)
        
        Args:
            transactions: List of Transaction objects, MUST be sorted by txn_date ASC
        """
        self.transactions = transactions
        self.dates = [t.txn_date for t in transactions]
        self.amounts = [t.amount for t in transactions]
    
    # ===== STEP 0: Inputs and invariants =====
    
    def validate_preconditions(self) -> bool:
        """Step 0: Check if we have enough data to proceed"""
        if len(self.transactions) < self.MIN_TRANSACTIONS_REQUIRED:
            return False
        
        # Verify sorted by date
        for i in range(len(self.dates) - 1):
            if self.dates[i] > self.dates[i + 1]:
                raise ValueError("Transactions must be sorted by date ASC")
        
        return True
    
    # ===== STEP 1: Prepare raw sequences (DO NOT AGGREGATE) =====
    # Already done in __init__ via self.dates and self.amounts
    
    # ===== STEP 2: Compute gap sequence (core signal) =====
    
    def compute_gap_sequence(self) -> Dict:
        """
        Step 2: Compute gaps between consecutive transactions.
        Returns primary signal for recurrence detection.
        """
        if len(self.dates) < 2:
            return {
                'gap_days': [],
                'avg_gap_days': 0.0,
                'stddev_gap_days': 0.0,
                'min_gap_days': 0.0,
                'max_gap_days': 0.0,
            }
        
        gap_days = []
        for i in range(len(self.dates) - 1):
            delta = self.dates[i + 1] - self.dates[i]
            gap_days.append(delta.days)
        
        return {
            'gap_days': gap_days,
            'avg_gap_days': statistics.mean(gap_days),
            'stddev_gap_days': statistics.stdev(gap_days) if len(gap_days) > 1 else 0.0,
            'min_gap_days': min(gap_days),
            'max_gap_days': max(gap_days),
        }
    
    # ===== STEP 3: Detect high-frequency noise (Case-6 early exit) =====
    
    def is_frequent_variable(self, gap_stats: Dict) -> bool:
        """
        Step 3: Check if this is high-frequency noise (groceries, daily spends).
        Returns True if pattern should be classified as FREQUENT_VARIABLE and exit.
        """
        if not gap_stats['gap_days']:
            return False
        
        # Compute transactions per 30 days
        total_days = (self.dates[-1] - self.dates[0]).days
        if total_days == 0:
            return False
        
        transactions_per_30_days = (len(self.transactions) / total_days) * 30
        
        logger.debug(f"[DISCOVERY_ENGINE] Frequency check: {transactions_per_30_days:.2f} txns/30days "
                    f"(threshold: {self.FREQUENT_THRESHOLD_PER_30_DAYS}), "
                    f"avg_gap: {gap_stats['avg_gap_days']:.1f}d, "
                    f"stddev_gap: {gap_stats['stddev_gap_days']:.1f}d")
        
        # High frequency + high variance = noise
        variance_threshold = gap_stats['avg_gap_days'] * 0.5
        is_high_frequency = transactions_per_30_days >= self.FREQUENT_THRESHOLD_PER_30_DAYS
        is_high_variance = gap_stats['stddev_gap_days'] > variance_threshold
        
        if is_high_frequency and is_high_variance:
            logger.warning(f"[DISCOVERY_ENGINE] Detected frequent variable pattern (not recurring): "
                          f"frequency={transactions_per_30_days:.2f} >= {self.FREQUENT_THRESHOLD_PER_30_DAYS}, "
                          f"variance={gap_stats['stddev_gap_days']:.1f} > {variance_threshold:.1f}")
            return True
        
        return False
    
    # ===== STEP 4: Amount-based clustering (CRITICAL STEP) =====
    
    def cluster_by_amount(self) -> List[AmountCluster]:
        """
        Step 4: Split transactions into amount-based clusters.
        One transactor can have multiple patterns (e.g., ₹100 and ₹1000 SIPs).
        
        Uses hybrid tolerance: max(₹50, amount × 25%)
        """
        if not self.transactions:
            return []
        
        # Sort by amount
        sorted_txns = sorted(self.transactions, key=lambda t: t.amount)
        
        clusters: List[AmountCluster] = []
        current_cluster: List[Transaction] = [sorted_txns[0]]
        
        for i in range(1, len(sorted_txns)):
            prev_amount = sorted_txns[i - 1].amount
            curr_amount = sorted_txns[i].amount
            
            # Hybrid tolerance
            tolerance = max(
                self.AMOUNT_TOLERANCE_ABSOLUTE,
                prev_amount * Decimal(str(self.AMOUNT_TOLERANCE_PERCENT))
            )
            
            if abs(curr_amount - prev_amount) <= tolerance:
                # Same cluster
                current_cluster.append(sorted_txns[i])
            else:
                # New cluster
                if len(current_cluster) >= self.MIN_TRANSACTIONS_REQUIRED:
                    clusters.append(self._create_cluster(current_cluster))
                current_cluster = [sorted_txns[i]]
        
        # Don't forget last cluster
        if len(current_cluster) >= self.MIN_TRANSACTIONS_REQUIRED:
            clusters.append(self._create_cluster(current_cluster))
        
        return clusters
    
    def _create_cluster(self, transactions: List[Transaction]) -> AmountCluster:
        """Helper to create AmountCluster from transactions"""
        amounts = [t.amount for t in transactions]
        avg_amount = sum(amounts) / len(amounts)
        
        # Coefficient of variation
        if avg_amount > 0:
            stddev = Decimal(str(statistics.stdev([float(a) for a in amounts]))) if len(amounts) > 1 else Decimal('0')
            cv = float(stddev / avg_amount)
        else:
            cv = 0.0
        
        return AmountCluster(
            transactions=sorted(transactions, key=lambda t: t.txn_date),  # Re-sort by date
            min_amount=min(amounts),
            max_amount=max(amounts),
            avg_amount=avg_amount,
            cv=cv
        )
    
    # ===== STEP 5: Time-consistency check per cluster =====
    
    def check_time_consistency(self, cluster: AmountCluster) -> Optional[Dict]:
        """
        Step 5: Recompute gap statistics for this amount cluster.
        Returns None if cluster fails time consistency (too frequent).
        """
        if len(cluster.transactions) < 2:
            return None
        
        dates = [t.txn_date for t in cluster.transactions]
        gap_days = []
        for i in range(len(dates) - 1):
            gap_days.append((dates[i + 1] - dates[i]).days)
        
        avg_gap = statistics.mean(gap_days)
        stddev_gap = statistics.stdev(gap_days) if len(gap_days) > 1 else 0.0
        
        # Reject if too frequent
        if avg_gap < self.MIN_INTERVAL_DAYS:
            return None
        
        return {
            'gap_days': gap_days,
            'avg_gap': avg_gap,
            'stddev_gap': stddev_gap,
            'min_gap': min(gap_days),
            'max_gap': max(gap_days),
        }
    
    # ===== STEP 6: Interval classification (deterministic) =====
    
    def classify_interval(self, time_stats: Dict) -> Optional[int]:
        """
        Step 6: Determine interval_days from gap statistics.
        Returns None if irregular (no stable interval).
        """
        avg_gap = time_stats['avg_gap']
        stddev_gap = time_stats['stddev_gap']
        
        # If variance is low, we have a stable interval
        if stddev_gap < avg_gap * 0.2:  # CV < 20%
            return round(avg_gap)
        
        # Irregular timing
        return None
    
    # ===== STEP 7: Deterministic case assignment (NO LLM YET) =====
    
    def classify_pattern_case(
        self,
        cluster: AmountCluster,
        time_stats: Dict,
        interval_days: Optional[int]
    ) -> PatternCase:
        """
        Step 7: Assign pattern case based on deterministic rules.
        NO LLM, NO guessing.
        """
        avg_gap = time_stats['avg_gap']
        
        # Check if present in most months (flexible monthly detection)
        if interval_days is None:
            if self._is_monthly_presence_high(cluster):
                return PatternCase.FLEXIBLE_MONTHLY
            else:
                return PatternCase.FREQUENT_VARIABLE  # Irregular and not monthly
        
        # Fixed interval cases
        if self.MONTHLY_RANGE[0] <= interval_days <= self.MONTHLY_RANGE[1]:
            return PatternCase.FIXED_MONTHLY
        elif self.BI_MONTHLY_RANGE[0] <= interval_days <= self.BI_MONTHLY_RANGE[1]:
            return PatternCase.BI_MONTHLY
        elif self.QUARTERLY_RANGE[0] <= interval_days <= self.QUARTERLY_RANGE[1]:
            return PatternCase.QUARTERLY
        else:
            return PatternCase.CUSTOM_INTERVAL
    
    def _is_monthly_presence_high(self, cluster: AmountCluster) -> bool:
        """Check if transactions appear in most calendar months"""
        if len(cluster.transactions) < self.MIN_TRANSACTIONS_REQUIRED:
            return False
        
        # Get unique months
        months_present = set()
        for txn in cluster.transactions:
            month_key = (txn.txn_date.year, txn.txn_date.month)
            months_present.add(month_key)
        
        # Calculate total months in date range
        first_date = cluster.transactions[0].txn_date
        last_date = cluster.transactions[-1].txn_date
        total_months = (last_date.year - first_date.year) * 12 + (last_date.month - first_date.month) + 1
        
        # Present in at least 60% of months?
        return len(months_present) >= total_months * 0.6
    
    # ===== STEP 8: Amount behavior classification (deterministic) =====
    
    def classify_amount_behavior(self, cluster: AmountCluster) -> AmountBehaviorType:
        """
        Step 8: Classify amount consistency using coefficient of variation.
        """
        cv = cluster.cv
        
        if cv < self.CV_FIXED_THRESHOLD:
            return AmountBehaviorType.FIXED
        elif cv < self.CV_VARIABLE_THRESHOLD:
            return AmountBehaviorType.VARIABLE
        else:
            return AmountBehaviorType.HIGHLY_VARIABLE
    
    # ===== STEP 9: Candidate validation gate =====
    
    def validate_candidate(
        self,
        cluster: AmountCluster,
        pattern_case: PatternCase,
        interval_days: Optional[int]
    ) -> bool:
        """
        Step 9: Final validation before accepting pattern.
        """
        # Must have minimum transactions
        if len(cluster.transactions) < self.MIN_TRANSACTIONS_REQUIRED:
            return False
        
        # Interval must be reasonable (except flexible monthly)
        if pattern_case != PatternCase.FLEXIBLE_MONTHLY:
            if interval_days is None or interval_days < 15:
                return False
        
        return True
    
    def compute_initial_confidence(
        self,
        cluster: AmountCluster,
        time_stats: Dict,
        amount_behavior: AmountBehaviorType
    ) -> float:
        """
        Compute initial confidence score (0.0 to 1.0) based on pattern quality.
        """
        # Base confidence from number of observations
        transaction_count = len(cluster.transactions)
        count_confidence = min(1.0, transaction_count / 12.0)  # Cap at 12 observations
        
        # Time consistency (lower stddev = higher confidence)
        avg_gap = time_stats['avg_gap']
        stddev_gap = time_stats['stddev_gap']
        time_cv = stddev_gap / avg_gap if avg_gap > 0 else 1.0
        time_confidence = max(0.0, 1.0 - time_cv)
        
        # Amount consistency
        amount_confidence = {
            AmountBehaviorType.FIXED: 1.0,
            AmountBehaviorType.VARIABLE: 0.8,
            AmountBehaviorType.HIGHLY_VARIABLE: 0.5,
        }[amount_behavior]
        
        # Weighted average
        confidence = (
            count_confidence * 0.3 +
            time_confidence * 0.4 +
            amount_confidence * 0.3
        )
        
        return round(confidence, 3)
    
    # ===== MAIN DISCOVERY METHOD =====
    
    def discover_patterns(self) -> List[PatternCandidate]:
        """
        Main entry point: Execute Steps 0-9 to discover patterns.
        Returns list of valid pattern candidates.
        """
        logger.info(f"[DISCOVERY_ENGINE] Starting pattern discovery with {len(self.transactions)} transactions")
        
        # Step 0: Validate preconditions
        logger.debug(f"[DISCOVERY_ENGINE] Step 0: Validating preconditions")
        if not self.validate_preconditions():
            logger.warning(f"[DISCOVERY_ENGINE] Preconditions failed")
            return []
        
        # Step 2: Compute gap sequence
        logger.debug(f"[DISCOVERY_ENGINE] Step 2: Computing gap sequence")
        gap_stats = self.compute_gap_sequence()
        logger.debug(f"[DISCOVERY_ENGINE] Gap stats: mean={gap_stats.get('mean', 0):.1f}d, median={gap_stats.get('median', 0):.1f}d")
        
        # Step 3: Check for high-frequency noise (early exit)
        logger.debug(f"[DISCOVERY_ENGINE] Step 3: Checking for high-frequency noise")
        if self.is_frequent_variable(gap_stats):
            # Could return a FREQUENT_VARIABLE pattern if needed
            # For now, return empty (these are not recurring patterns)
            return []
        
        # Step 4: Amount-based clustering
        logger.debug(f"[DISCOVERY_ENGINE] Step 4: Clustering transactions by amount")
        clusters = self.cluster_by_amount()
        logger.debug(f"[DISCOVERY_ENGINE] Found {len(clusters)} amount clusters")
        
        if not clusters:
            logger.warning(f"[DISCOVERY_ENGINE] No amount clusters found")
            return []
        
        # Steps 5-9: Process each cluster
        logger.debug(f"[DISCOVERY_ENGINE] Steps 5-9: Processing each cluster")
        candidates: List[PatternCandidate] = []
        
        for cluster_idx, cluster in enumerate(clusters, 1):
            logger.debug(f"[DISCOVERY_ENGINE] Processing cluster {cluster_idx}/{len(clusters)}: "
                        f"{len(cluster.transactions)} transactions, avg_amount={cluster.avg_amount:.2f}")
            
            # Step 5: Time-consistency check
            logger.debug(f"[DISCOVERY_ENGINE] Step 5: Checking time consistency for cluster {cluster_idx}")
            time_stats = self.check_time_consistency(cluster)
            if time_stats is None:
                logger.debug(f"[DISCOVERY_ENGINE] Cluster {cluster_idx} failed time consistency check")
                continue  # Reject cluster
            
            # Step 6: Interval classification
            logger.debug(f"[DISCOVERY_ENGINE] Step 6: Classifying interval for cluster {cluster_idx}")
            interval_days = self.classify_interval(time_stats)
            logger.debug(f"[DISCOVERY_ENGINE] Cluster {cluster_idx} interval: {interval_days} days")
            
            # Step 7: Pattern case assignment
            logger.debug(f"[DISCOVERY_ENGINE] Step 7: Assigning pattern case for cluster {cluster_idx}")
            pattern_case = self.classify_pattern_case(cluster, time_stats, interval_days)
            logger.debug(f"[DISCOVERY_ENGINE] Cluster {cluster_idx} pattern case: {pattern_case.value}")
            
            # Skip frequent variable patterns
            if pattern_case == PatternCase.FREQUENT_VARIABLE:
                logger.debug(f"[DISCOVERY_ENGINE] Skipping cluster {cluster_idx}: frequent variable pattern")
                continue
            
            # Step 8: Amount behavior classification
            logger.debug(f"[DISCOVERY_ENGINE] Step 8: Classifying amount behavior for cluster {cluster_idx}")
            amount_behavior = self.classify_amount_behavior(cluster)
            logger.debug(f"[DISCOVERY_ENGINE] Cluster {cluster_idx} amount behavior: {amount_behavior.value}")
            
            # Step 9: Validation gate
            logger.debug(f"[DISCOVERY_ENGINE] Step 9: Validating candidate for cluster {cluster_idx}")
            if not self.validate_candidate(cluster, pattern_case, interval_days):
                logger.debug(f"[DISCOVERY_ENGINE] Cluster {cluster_idx} failed validation gate")
                continue
            
            # Compute confidence
            confidence = self.compute_initial_confidence(cluster, time_stats, amount_behavior)
            logger.debug(f"[DISCOVERY_ENGINE] Cluster {cluster_idx} confidence: {confidence:.2f}")
            
            # Create candidate
            candidate = PatternCandidate(
                cluster=cluster,
                pattern_case=pattern_case,
                amount_behavior=amount_behavior,
                interval_days=interval_days,
                avg_gap_days=time_stats['avg_gap'],
                stddev_gap_days=time_stats['stddev_gap'],
                confidence=confidence,
                transactions=cluster.transactions
            )
            
            candidates.append(candidate)
            logger.info(f"[DISCOVERY_ENGINE] Created candidate {len(candidates)}: "
                       f"{pattern_case.value}, {amount_behavior.value}, interval={interval_days}d, confidence={confidence:.2f}")
        
        logger.info(f"[DISCOVERY_ENGINE] Pattern discovery complete: {len(candidates)} candidates found")
        return candidates


# ===== HELPER FUNCTIONS =====

def days_between(date1: datetime, date2: datetime) -> int:
    """Calculate days between two dates"""
    return abs((date2 - date1).days)
