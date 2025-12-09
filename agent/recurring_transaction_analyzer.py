"""
Recurring Transaction Analyzer Agent

AI-powered agent that detects recurring transaction patterns using Google ADK LLM.
Focuses on rent, family transactions, regular payments with intelligent pattern recognition.
Different from bills - emphasizes personal transactions with consistent amounts.
"""

import logging
import json
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
import statistics
import os

from dotenv import load_dotenv
from google.adk.agents.llm_agent import Agent

from app.models.transaction import Transaction
from app.models.transactor import Transactor
from app.models.category import Category
from app.models.spending_pattern import SpendingPattern
from app.models.pattern_transaction import PatternTransaction

load_dotenv()
logger = logging.getLogger(__name__)


class RecurringTransactionAnalyzer:
    """
    AI-powered analyzer for detecting recurring transaction patterns using Google ADK LLM.
    
    Focuses on personal recurring transactions:
    - Rent, family transfers, loan payments
    - Regular shopping and routine expenses
    - More consistent amounts than bills
    - Personal relationship-based patterns
    """
    
    def __init__(self, db: Session, min_occurrences: int = 3, min_days_history: int = 60):
        """
        Initialize Recurring Transaction Analyzer with LLM agent.
        
        Args:
            db: Database session
            min_occurrences: Minimum number of transactions to consider a pattern (default: 3)
            min_days_history: Minimum days of transaction history required (default: 60)
        """
        self.db = db
        self.min_occurrences = min_occurrences
        self.min_days_history = min_days_history
        
        # Initialize Google ADK Agent for pattern analysis
        self.agent = Agent(
            model="gemini-2.0-flash-exp",
            name="recurring_transaction_analyzer_agent",
            description="AI agent specialized in detecting recurring personal transaction patterns",
            instruction=self._get_system_instruction()
        )
    
    def _get_system_instruction(self) -> str:
        """Get system instruction for the LLM agent"""
        return """You are an expert financial analyst specializing in identifying recurring personal transaction patterns.

Your task is to analyze transaction data and identify recurring patterns for personal expenses and transfers.

## Recurring Pattern Characteristics:
1. **Rent/Housing**: Monthly payments to landlords or property managers - very consistent
2. **Family Transfers**: Regular money sent to family members - consistent amounts and timing
3. **Loan/EMI**: Fixed installment payments - highly consistent
4. **Savings**: SIP, RD, recurring deposits - fixed amounts and frequencies
5. **Routine Shopping**: Regular grocery stores, fuel stations - may vary but show patterns
6. **Education**: Tuition, coaching fees - consistent monthly/quarterly payments

## Analysis Guidelines:
- Look for personal transaction patterns (not bills/utilities)
- Identify consistent frequencies (weekly, bi-weekly, monthly)
- Amount consistency is MORE important than for bills
- Detect if this is truly a recurring pattern vs occasional spending
- Consider the nature of transactor (person vs company)
- Provide confidence score based on consistency

## Output Format:
Return a JSON object with:
{
  "is_recurring_pattern": boolean,
  "confidence": float (0-100),
  "pattern_type": "recurring_transaction",
  "pattern_name": string,
  "frequency_analysis": {
    "average_days": int,
    "variance_days": int,
    "frequency_label": string
  },
  "amount_analysis": {
    "is_consistent": boolean,
    "consistency_note": string
  },
  "reasoning": string (explain why this is or isn't a recurring pattern)
}

Be selective - only identify clear recurring patterns with good confidence (≥40)."""
    
    def _analyze_with_llm(
        self,
        transactor_name: str,
        category_label: Optional[str],
        transaction_data: List[Dict]
    ) -> Optional[Dict]:
        """
        Use LLM to analyze if transactions form a recurring pattern.
        
        Args:
            transactor_name: Name of the transactor
            category_label: Category label
            transaction_data: List of transaction details with dates and amounts
        
        Returns:
            LLM analysis result or None
        """
        # Prepare context for LLM
        context = f"""Analyze these transactions to determine if they form a recurring personal transaction pattern:

Transactor: {transactor_name}
Category: {category_label or 'Unknown'}

Transactions ({len(transaction_data)} total):
"""
        for i, txn in enumerate(transaction_data, 1):
            context += f"\n{i}. Date: {txn['date']}, Amount: ₹{txn['amount']:.2f}"
        
        # Calculate intervals for context
        if len(transaction_data) >= 2:
            intervals = []
            for i in range(1, len(transaction_data)):
                delta = (transaction_data[i]['date'] - transaction_data[i-1]['date']).days
                intervals.append(delta)
            context += f"\n\nCalculated intervals (days between transactions): {intervals}"
        
        context += "\n\nProvide your analysis in JSON format as specified."
        
        try:
            # Query the LLM using Google GenAI Client
            from google.genai import Client
            client = Client()
            
            prompt = f"""{self._get_system_instruction()}
            
            {context}"""
            
            response = client.models.generate_content(
                model="gemini-2.0-flash-exp",
                contents=prompt,
            )
            
            # Parse JSON response
            response_text = response.text
            
            # Extract JSON from response (handle markdown code blocks)
            json_str = response_text
            if '```json' in json_str:
                json_str = json_str.split('```json')[1].split('```')[0].strip()
            elif '```' in json_str:
                json_str = json_str.split('```')[1].split('```')[0].strip()
            
            result = json.loads(json_str)
            logger.info(f"LLM analysis for {transactor_name}: {result.get('reasoning', 'No reasoning')}")
            return result
        
        except Exception as e:
            logger.error(f"Error in LLM analysis for {transactor_name}: {str(e)}")
            return None
    
    def _calculate_intervals(self, transaction_dates: List[datetime]) -> List[int]:
        """
        Calculate intervals (in days) between consecutive transactions.
        
        Args:
            transaction_dates: List of transaction dates (sorted)
        
        Returns:
            List of intervals in days
        """
        intervals = []
        for i in range(1, len(transaction_dates)):
            delta = transaction_dates[i] - transaction_dates[i-1]
            intervals.append(delta.days)
        return intervals
    
    def _detect_frequency(self, intervals: List[int]) -> Optional[Tuple[int, int, str]]:
        """
        Detect frequency pattern from intervals.
        
        Args:
            intervals: List of intervals in days
        
        Returns:
            Tuple of (frequency_days, variance_days, frequency_label) or None
        """
        if not intervals or len(intervals) < 2:
            return None
        
        # Calculate average and standard deviation
        avg_interval = statistics.mean(intervals)
        std_dev = statistics.stdev(intervals) if len(intervals) > 1 else 0
        
        # For recurring transactions, we expect lower variance than bills
        # If variance is too high, might not be a true pattern
        if std_dev > avg_interval * 0.3:  # More than 30% variance
            logger.debug(f"High variance detected: {std_dev} for average {avg_interval}")
            # Still return, but with higher variance allowance
        
        # Round to nearest day
        frequency_days = round(avg_interval)
        variance_days = max(2, round(std_dev * 1.5))  # At least ±2 days variance
        
        # Generate human-readable label
        if 27 <= frequency_days <= 33:
            frequency_label = "Monthly"
        elif 13 <= frequency_days <= 16:
            frequency_label = "Bi-weekly"
        elif 6 <= frequency_days <= 8:
            frequency_label = "Weekly"
        elif 3 <= frequency_days <= 4:
            frequency_label = "Every 3-4 days"
        elif 1 <= frequency_days <= 2:
            frequency_label = "Daily"
        elif 58 <= frequency_days <= 65:
            frequency_label = "Bi-monthly"
        elif 88 <= frequency_days <= 95:
            frequency_label = "Quarterly"
        else:
            frequency_label = f"Every {frequency_days} days"
        
        return (frequency_days, variance_days, frequency_label)
    
    def _calculate_amount_stats(self, amounts: List[float]) -> Dict:
        """
        Calculate amount statistics.
        
        Args:
            amounts: List of transaction amounts
        
        Returns:
            Dictionary with amount statistics
        """
        if not amounts:
            return {}
        
        avg_amount = statistics.mean(amounts)
        min_amount = min(amounts)
        max_amount = max(amounts)
        
        # Calculate variance percentage
        if avg_amount > 0:
            variance_percentage = ((max_amount - min_amount) / avg_amount) * 100
        else:
            variance_percentage = 0
        
        return {
            'average_amount': round(avg_amount, 2),
            'min_amount': round(min_amount, 2),
            'max_amount': round(max_amount, 2),
            'amount_variance_percentage': round(variance_percentage, 2)
        }
    
    def _is_amount_consistent(self, amounts: List[float], tolerance_percentage: float = 15.0) -> bool:
        """
        Check if amounts are relatively consistent.
        
        Args:
            amounts: List of amounts
            tolerance_percentage: Allowed variance percentage (default: 15%)
        
        Returns:
            True if amounts are within tolerance
        """
        if not amounts or len(amounts) < 2:
            return True
        
        avg_amount = statistics.mean(amounts)
        if avg_amount == 0:
            return False
        
        # Check if all amounts are within tolerance of average
        for amount in amounts:
            deviation_percentage = abs((amount - avg_amount) / avg_amount * 100)
            if deviation_percentage > tolerance_percentage:
                return False
        
        return True
    
    def _predict_next_transaction(
        self, 
        last_date: datetime, 
        frequency_days: int
    ) -> datetime:
        """
        Predict next transaction date.
        
        Args:
            last_date: Date of last transaction
            frequency_days: Detected frequency in days
        
        Returns:
            Predicted next transaction date
        """
        return last_date + timedelta(days=frequency_days)
    
    def analyze_user_recurring_transactions(self, user_id: str) -> List[SpendingPattern]:
        """
        Analyze all transactions for a user and detect recurring transaction patterns.
        
        Args:
            user_id: User ID
        
        Returns:
            List of detected spending patterns
        """
        logger.info(f"Starting recurring transaction analysis for user {user_id}")
        
        # Check if user has sufficient transaction history
        oldest_transaction = self.db.query(Transaction).filter(
            Transaction.user_id == user_id
        ).order_by(Transaction.date.asc()).first()
        
        if not oldest_transaction:
            logger.info(f"No transactions found for user {user_id}")
            return []
        
        days_history = (datetime.now(timezone.utc) - oldest_transaction.date).days
        if days_history < self.min_days_history:
            logger.info(
                f"Insufficient transaction history for user {user_id}: "
                f"{days_history} days (minimum: {self.min_days_history})"
            )
            return []
        
        # Get all transactions with transactors
        transactions = self.db.query(Transaction).filter(
            Transaction.user_id == user_id,
            Transaction.transactor_id.isnot(None)
        ).order_by(Transaction.date.asc()).all()
        
        # Group transactions by transactor
        transactor_groups = defaultdict(list)
        for txn in transactions:
            transactor_groups[txn.transactor_id].append(txn)
        
        detected_patterns = []
        
        # Analyze each transactor group
        for transactor_id, txn_list in transactor_groups.items():
            if len(txn_list) < self.min_occurrences:
                continue
            
            transactor = self.db.query(Transactor).filter(
                Transactor.id == transactor_id
            ).first()
            
            if not transactor:
                continue
            
            # Get category from first transaction (assuming consistent category)
            category = txn_list[0].category if txn_list[0].category_id else None
            
            # Extract dates and amounts
            dates = [txn.date for txn in txn_list]
            amounts = [float(txn.amount) for txn in txn_list]
            
            # Prepare transaction data for LLM analysis
            transaction_data = [
                {'date': txn.date, 'amount': float(txn.amount)}
                for txn in txn_list
            ]
            
            # Use LLM to analyze if this is a recurring pattern
            llm_analysis = self._analyze_with_llm(
                transactor_name=transactor.name,
                category_label=category.label if category else None,
                transaction_data=transaction_data
            )
            
            # Skip if LLM determines it's not a recurring pattern or low confidence
            if not llm_analysis or not llm_analysis.get('is_recurring_pattern', False):
                logger.debug(
                    f"LLM determined {transactor.name} is not a recurring pattern: "
                    f"{llm_analysis.get('reasoning', 'No reasoning') if llm_analysis else 'Analysis failed'}"
                )
                continue
            
            # Use LLM-provided confidence
            llm_confidence = llm_analysis.get('confidence', 0)
            
            # Use LLM confidence
            confidence_score = llm_analysis.get('confidence', 0)
            
            # Skip patterns with very low confidence
            if confidence_score < 40:
                logger.debug(
                    f"Skipping low confidence pattern for {transactor.name}: {confidence_score}%"
                )
                continue
            
            # Get LLM frequency analysis or calculate as fallback
            llm_freq = llm_analysis.get('frequency_analysis', {})
            frequency_days = llm_freq.get('average_days')
            variance_days = llm_freq.get('variance_days')
            frequency_label = llm_freq.get('frequency_label')
            
            # If LLM didn't provide frequency, calculate it
            if not frequency_days:
                intervals = self._calculate_intervals(dates)
                frequency_result = self._detect_frequency(intervals)
                if not frequency_result:
                    continue
                frequency_days, variance_days, frequency_label = frequency_result
            
            # Calculate amount statistics
            amount_stats = self._calculate_amount_stats(amounts)
            
            # Predict next transaction
            last_date = dates[-1]
            next_expected_date = self._predict_next_transaction(last_date, frequency_days)
            
            # Use LLM-suggested pattern name or generate default
            pattern_name = llm_analysis.get('pattern_name', f"{transactor.name}")
            
            # Create spending pattern
            pattern = SpendingPattern(
                user_id=user_id,
                transactor_id=transactor_id,
                category_id=txn_list[0].category_id,
                pattern_type='recurring_transaction',
                pattern_name=pattern_name,
                frequency_days=frequency_days,
                frequency_label=frequency_label,
                frequency_variance_days=variance_days,
                average_amount=amount_stats.get('average_amount'),
                min_amount=amount_stats.get('min_amount'),
                max_amount=amount_stats.get('max_amount'),
                amount_variance_percentage=amount_stats.get('amount_variance_percentage'),
                last_transaction_date=last_date,
                next_expected_date=next_expected_date,
                expected_amount=amount_stats.get('average_amount'),
                occurrence_count=len(txn_list),
                confidence_score=confidence_score,
                status='active',
                is_confirmed=False,
                detected_by_agent='recurring_transaction_agent_llm',
                detection_method=f"LLM Analysis: {llm_analysis.get('reasoning', 'Pattern detected')}",
                first_transaction_date=dates[0]
            )
            
            self.db.add(pattern)
            self.db.flush()  # Get pattern ID
            
            # Link transactions to pattern
            for txn in txn_list:
                pattern_txn = PatternTransaction(
                    pattern_id=pattern.id,
                    transaction_id=txn.id,
                    is_anomaly=False
                )
                self.db.add(pattern_txn)
            
            detected_patterns.append(pattern)
            logger.info(
                f"Detected recurring pattern: {pattern_name} for user {user_id}, "
                f"frequency: {frequency_label} ({frequency_days}±{variance_days} days), "
                f"confidence: {confidence_score}%"
            )
        
        self.db.commit()
        logger.info(
            f"Completed recurring transaction analysis for user {user_id}. "
            f"Found {len(detected_patterns)} patterns."
        )
        
        return detected_patterns
