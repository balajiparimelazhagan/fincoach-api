"""
Pattern Analyzer Coordinator - LLM Agent

LLM-powered coordinator that intelligently orchestrates pattern analysis.
Uses Google Gemini to decide which analyzers to run and how to handle results.
"""

import logging
import json
from typing import List, Optional, Dict
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta, timezone

from app.models.spending_pattern import SpendingPattern
from app.models.transaction import Transaction
from app.models.transactor import Transactor
from agent.bill_pattern_analyzer import BillPatternAnalyzer
from agent.recurring_transaction_analyzer import RecurringTransactionAnalyzer

logger = logging.getLogger(__name__)


class PatternAnalyzerCoordinator:
    """
    LLM-powered coordinator that orchestrates pattern analysis intelligently.
    
    Uses Google Gemini to:
    1. Analyze user transaction data and determine optimal analysis strategy
    2. Fetch and prepare data for sub-agents
    3. Coordinate bill and recurring transaction analyzers
    4. Make intelligent decisions about pattern conflicts
    5. Provide reasoning for coordination decisions
    """
    
    def __init__(
        self, 
        db: Session, 
        min_occurrences: int = 3, 
        min_days_history: int = 60
    ):
        """
        Initialize LLM-powered Pattern Analyzer Coordinator.
        
        Args:
            db: Database session
            min_occurrences: Minimum number of transactions to consider a pattern
            min_days_history: Minimum days of transaction history required
        """
        self.db = db
        self.min_occurrences = min_occurrences
        self.min_days_history = min_days_history
        
        # Initialize analyzer agents (lazy loading)
        self._bill_analyzer = None
        self._recurring_analyzer = None
        
        # LLM configuration (client created per request like other analyzers)
        self.llm_model = 'gemini-2.0-flash-exp'
        logger.info("🤖 LLM Coordinator initialized with Gemini 2.0 Flash Exp")
    
    def _get_bill_analyzer(self) -> BillPatternAnalyzer:
        """Lazy load bill analyzer"""
        if self._bill_analyzer is None:
            self._bill_analyzer = BillPatternAnalyzer(
                db=self.db,
                min_occurrences=self.min_occurrences,
                min_days_history=self.min_days_history
            )
        return self._bill_analyzer
    
    def _get_recurring_analyzer(self) -> RecurringTransactionAnalyzer:
        """Lazy load recurring transaction analyzer"""
        if self._recurring_analyzer is None:
            self._recurring_analyzer = RecurringTransactionAnalyzer(
                db=self.db,
                min_occurrences=self.min_occurrences,
                min_days_history=self.min_days_history
            )
        return self._recurring_analyzer
    
    def _fetch_user_transactors(self, user_id: str) -> List[Dict]:
        """
        Fetch all transactors and their transaction data for the user.
        This is the data coordinator feeds to sub-agents.
        
        Args:
            user_id: User ID
        
        Returns:
            List of transactor dictionaries with transaction details
        """
        logger.info(f"Fetching transactor data for user {user_id}")
        
        # Get all transactors with at least min_occurrences transactions
        transactor_data = []
        
        transactors = self.db.query(
            Transactor.id,
            Transactor.name,
            Transactor.source_id,
            func.count(Transaction.id).label('transaction_count'),
            func.min(Transaction.date).label('first_transaction'),
            func.max(Transaction.date).label('last_transaction')
        ).join(
            Transaction, Transaction.transactor_id == Transactor.id
        ).filter(
            Transaction.user_id == user_id
        ).group_by(
            Transactor.id, Transactor.name, Transactor.source_id
        ).having(
            func.count(Transaction.id) >= self.min_occurrences
        ).all()
        
        logger.info(f"Found {len(transactors)} transactors with {self.min_occurrences}+ transactions")
        
        for t in transactors:
            # Check if enough transaction history
            if t.first_transaction:
                days_history = (datetime.now(timezone.utc) - t.first_transaction).days
                if days_history < self.min_days_history:
                    logger.debug(f"Skipping transactor {t.name}: only {days_history} days of history")
                    continue
            
            transactor_data.append({
                'transactor_id': str(t.id),
                'name': t.name,
                'source_id': t.source_id,
                'transaction_count': t.transaction_count,
                'first_transaction': t.first_transaction,
                'last_transaction': t.last_transaction
            })
        
        logger.info(f"Prepared data for {len(transactor_data)} transactors meeting criteria")
        return transactor_data
    
    def _llm_decide_analysis_strategy(self, transactor_data: List[dict]) -> dict:
        """
        Use LLM to analyze transactor data and decide analysis strategy.
        
        Args:
            transactor_data: List of transactor data dictionaries
        
        Returns:
            Dictionary with LLM decisions and reasoning
        """
        if not transactor_data:
            return {
                'should_analyze_bills': True,
                'should_analyze_recurring': True,
                'priority': 'both',
                'reasoning': 'No transactor data available'
            }
        
        try:
            # Prepare transactor summary for LLM
            transactor_summary = []
            for t in transactor_data[:10]:  # Limit to 10 for context
                transactor_summary.append({
                    'name': t['name'],
                    'transaction_count': t['transaction_count'],
                    'days_of_history': (t['last_transaction'] - t['first_transaction']).days if t['first_transaction'] and t['last_transaction'] else 0
                })
            
            prompt = f"""You are an AI coordinator analyzing financial transaction patterns.

Given these transactors with multiple transactions:
{json.dumps(transactor_summary, indent=2)}

Analyze this data and provide strategic guidance:
1. Should we run bill pattern analysis? (utilities, subscriptions, telecom)
2. Should we run recurring transaction analysis? (rent, family transfers, loans)
3. Which should have priority if resources are limited?
4. Any specific transactors that stand out?

Respond in JSON format:
{{
  "should_analyze_bills": true/false,
  "should_analyze_recurring": true/false,
  "priority": "bills" or "recurring" or "both",
  "reasoning": "explanation of your decision",
  "notable_transactors": ["list of interesting transactor names"]
}}"""
            
            # Create client per request (like other analyzers)
            from google.genai import Client
            client = Client()
            
            response = client.models.generate_content(
                model=self.llm_model,
                contents=prompt
            )
            
            # Parse LLM response
            response_text = response.text.strip()
            if response_text.startswith('```json'):
                response_text = response_text[7:-3].strip()
            elif response_text.startswith('```'):
                response_text = response_text[3:-3].strip()
            
            decision = json.loads(response_text)
            logger.info(f"🤖 LLM Coordinator Decision: {decision['reasoning']}")
            return decision
            
        except Exception as e:
            logger.error(f"LLM coordinator decision failed: {e}")
            return {
                'should_analyze_bills': True,
                'should_analyze_recurring': True,
                'priority': 'both',
                'reasoning': f'Fallback strategy (LLM error: {str(e)})'
            }
    
    def _get_existing_patterns(self, user_id: str) -> List[SpendingPattern]:
        """
        Get existing patterns for a user.
        
        Args:
            user_id: User ID
        
        Returns:
            List of existing spending patterns
        """
        return self.db.query(SpendingPattern).filter(
            SpendingPattern.user_id == user_id
        ).all()
    
    def _pattern_exists(
        self, 
        existing_patterns: List[SpendingPattern], 
        transactor_id: str,
        pattern_type: str
    ) -> bool:
        """
        Check if a pattern already exists for a transactor.
        
        Args:
            existing_patterns: List of existing patterns
            transactor_id: Transactor ID to check
            pattern_type: Type of pattern ('bill' or 'recurring_transaction')
        
        Returns:
            True if pattern exists
        """
        for pattern in existing_patterns:
            if (pattern.transactor_id == transactor_id and 
                pattern.pattern_type == pattern_type and
                pattern.status == 'active'):
                return True
        return False
    
    def analyze_all_patterns(self, user_id: str, force_reanalyze: bool = False) -> dict:
        """
        Orchestrate pattern analysis for a user.
        Coordinator fetches data and feeds it to sub-agents.
        
        Args:
            user_id: User ID
            force_reanalyze: If True, reanalyze even if patterns exist
        
        Returns:
            Dictionary with analysis results
        """
        logger.info(f"🎯 Pattern Coordinator: Starting analysis for user {user_id}")
        
        # Check for existing patterns
        existing_patterns = self._get_existing_patterns(user_id)
        
        if existing_patterns and not force_reanalyze:
            logger.info(
                f"User {user_id} already has {len(existing_patterns)} patterns. "
                f"Skipping analysis. Use force_reanalyze=True to override."
            )
            return {
                'status': 'skipped',
                'reason': 'patterns_already_exist',
                'existing_pattern_count': len(existing_patterns),
                'bill_patterns': [],
                'recurring_patterns': [],
                'bill_patterns_count': 0,
                'recurring_patterns_count': 0,
                'total_patterns': len(existing_patterns),
                'duplicates_removed': 0
            }
        
        # If force_reanalyze is True and patterns exist, delete them first
        if existing_patterns and force_reanalyze:
            logger.info(
                f"🔄 Force reanalyze enabled: Deleting {len(existing_patterns)} existing patterns "
                f"for user {user_id}"
            )
            
            # Import models for deletion
            from app.models.pattern_transaction import PatternTransaction
            from app.models.pattern_user_feedback import PatternUserFeedback
            
            pattern_ids = [p.id for p in existing_patterns]
            
            # Delete associated records first (foreign key constraints)
            deleted_txn_links = self.db.query(PatternTransaction).filter(
                PatternTransaction.pattern_id.in_(pattern_ids)
            ).delete(synchronize_session=False)
            
            deleted_feedback = self.db.query(PatternUserFeedback).filter(
                PatternUserFeedback.pattern_id.in_(pattern_ids)
            ).delete(synchronize_session=False)
            
            # Delete patterns
            deleted_patterns = self.db.query(SpendingPattern).filter(
                SpendingPattern.id.in_(pattern_ids)
            ).delete(synchronize_session=False)
            
            self.db.commit()
            
            logger.info(
                f"✅ Cleanup complete: Deleted {deleted_patterns} patterns, "
                f"{deleted_txn_links} transaction links, {deleted_feedback} feedback records. "
                f"Starting fresh analysis..."
            )
        
        # STEP 1: Fetch and prepare transactor data
        logger.info(f"📊 Coordinator: Fetching transactor data for user {user_id}")
        transactor_data = self._fetch_user_transactors(user_id)
        
        if not transactor_data:
            logger.warning(f"No transactors found for user {user_id} meeting criteria")
            return {
                'status': 'completed',
                'reason': 'no_transactors_meeting_criteria',
                'bill_patterns': [],
                'recurring_patterns': [],
                'bill_patterns_count': 0,
                'recurring_patterns_count': 0,
                'total_patterns': 0,
                'duplicates_removed': 0
            }
        
        logger.info(f"📦 Coordinator: Prepared {len(transactor_data)} transactors for analysis")
        
        # STEP 2: LLM Coordinator decides strategy
        logger.info(f"🤖 Coordinator: Using LLM to decide analysis strategy")
        llm_decision = self._llm_decide_analysis_strategy(transactor_data)
        logger.info(
            f"🎯 LLM Strategy Decision: "
            f"Bills={llm_decision['should_analyze_bills']}, "
            f"Recurring={llm_decision['should_analyze_recurring']}, "
            f"Priority={llm_decision['priority']}"
        )
        logger.info(f"💭 LLM Reasoning: {llm_decision['reasoning']}")
        
        bill_patterns = []
        recurring_patterns = []
        
        # STEP 3: Run Bill Pattern Analyzer (if LLM decides)
        if llm_decision['should_analyze_bills']:
            logger.info(f"💡 Coordinator: Triggering Bill Pattern Analyzer for user {user_id}")
            logger.info(f"📤 Feeding {len(transactor_data)} transactors to Bill Analyzer")
            bill_analyzer = self._get_bill_analyzer()
            bill_patterns = bill_analyzer.analyze_user_bills(user_id)
            logger.info(f"✅ Bill Analyzer found {len(bill_patterns)} bill patterns")
        else:
            logger.info(f"⏭️ Coordinator: Skipping Bill Analyzer per LLM decision")
        
        # STEP 4: Run Recurring Transaction Analyzer (if LLM decides)
        if llm_decision['should_analyze_recurring']:
            logger.info(f"💡 Coordinator: Triggering Recurring Transaction Analyzer for user {user_id}")
            logger.info(f"📤 Feeding {len(transactor_data)} transactors to Recurring Analyzer")
            recurring_analyzer = self._get_recurring_analyzer()
            recurring_patterns = recurring_analyzer.analyze_user_recurring_transactions(user_id)
            logger.info(f"✅ Recurring Analyzer found {len(recurring_patterns)} recurring patterns")
        else:
            logger.info(f"⏭️ Coordinator: Skipping Recurring Analyzer per LLM decision")
        
        # STEP 5: Intelligent de-duplication (Coordinator decides conflicts)
        logger.info(f"🔍 Coordinator: Analyzing pattern conflicts and duplicates")
        bill_transactor_ids = {p.transactor_id for p in bill_patterns}
        filtered_recurring = [
            p for p in recurring_patterns 
            if p.transactor_id not in bill_transactor_ids
        ]
        
        # If duplicates were removed, delete them from database
        duplicates_removed = 0
        if len(filtered_recurring) < len(recurring_patterns):
            duplicate_count = len(recurring_patterns) - len(filtered_recurring)
            duplicate_ids = [
                p.id for p in recurring_patterns 
                if p.transactor_id in bill_transactor_ids
            ]
            
            # Delete duplicate patterns and their associations
            self.db.query(SpendingPattern).filter(
                SpendingPattern.id.in_(duplicate_ids)
            ).delete(synchronize_session=False)
            self.db.commit()
            
            duplicates_removed = duplicate_count
            logger.info(
                f"🧹 Coordinator: Removed {duplicate_count} duplicate patterns "
                f"(bill patterns take priority over recurring)"
            )
        
        total_patterns = len(bill_patterns) + len(filtered_recurring)
        
        logger.info(
            f"🎉 Coordinator: Analysis completed for user {user_id}. "
            f"Total patterns: {total_patterns} "
            f"(Bill: {len(bill_patterns)}, Recurring: {len(filtered_recurring)}, Duplicates removed: {duplicates_removed})"
        )
        
        return {
            'status': 'completed',
            'total_patterns': total_patterns,
            'bill_patterns': bill_patterns,
            'recurring_patterns': filtered_recurring,
            'bill_patterns_count': len(bill_patterns),
            'recurring_patterns_count': len(filtered_recurring),
            'duplicates_removed': duplicates_removed
        }
    
    def update_patterns_for_new_transaction(
        self, 
        user_id: str, 
        transaction_id: str
    ) -> dict:
        """
        Update existing patterns when a new transaction is added.
        Re-analyze to see if the new transaction fits existing patterns or creates new ones.
        
        Args:
            user_id: User ID
            transaction_id: New transaction ID
        
        Returns:
            Dictionary with update results
        """
        logger.info(
            f"Updating patterns for user {user_id} with new transaction {transaction_id}"
        )
        
        # For now, we'll do a simple reanalysis
        # In future, this could be optimized to only update affected patterns
        result = self.analyze_all_patterns(user_id, force_reanalyze=True)
        
        return {
            'status': 'updated',
            'transaction_id': transaction_id,
            'analysis_result': result
        }
    
    def reanalyze_pattern(self, pattern_id: str) -> Optional[SpendingPattern]:
        """
        Reanalyze a specific pattern with updated transaction data.
        
        Args:
            pattern_id: Pattern ID to reanalyze
        
        Returns:
            Updated spending pattern or None
        """
        pattern = self.db.query(SpendingPattern).filter(
            SpendingPattern.id == pattern_id
        ).first()
        
        if not pattern:
            logger.warning(f"Pattern {pattern_id} not found")
            return None
        
        logger.info(f"Reanalyzing pattern {pattern_id} ({pattern.pattern_name})")
        
        # Determine which analyzer to use
        if pattern.pattern_type == 'bill':
            analyzer = self.bill_analyzer
        else:
            analyzer = self.recurring_analyzer
        
        # For now, we'll trigger a full reanalysis for the user
        # This ensures consistency across all patterns
        self.analyze_all_patterns(pattern.user_id, force_reanalyze=True)
        
        # Fetch updated pattern
        updated_pattern = self.db.query(SpendingPattern).filter(
            SpendingPattern.id == pattern_id
        ).first()
        
        return updated_pattern
