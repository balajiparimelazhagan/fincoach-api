"""
Pattern Analysis Quick Start Example

This script demonstrates how to use the deterministic pattern analysis system.
"""
from datetime import datetime
from decimal import Decimal

from agent.pattern_discovery_engine import (
    DeterministicPatternDiscovery,
    Transaction,
    PatternCase,
    AmountBehaviorType
)
from agent.pattern_obligation_manager import PatternObligationManager
from agent.pattern_explanation_agent import PatternExplanationAgent


# ==============================================================================
# EXAMPLE 1: Discover patterns from transaction data
# ==============================================================================

def example_discover_patterns():
    """
    Example: Discover recurring patterns from Netflix subscription transactions.
    """
    print("=" * 80)
    print("EXAMPLE 1: Pattern Discovery")
    print("=" * 80)
    
    # Sample transactions: Netflix subscription (₹840 monthly)
    transactions = [
        Transaction(txn_id="1", txn_date=datetime(2025, 8, 15), amount=Decimal("840")),
        Transaction(txn_id="2", txn_date=datetime(2025, 9, 15), amount=Decimal("840")),
        Transaction(txn_id="3", txn_date=datetime(2025, 10, 15), amount=Decimal("840")),
        Transaction(txn_id="4", txn_date=datetime(2025, 11, 15), amount=Decimal("840")),
        Transaction(txn_id="5", txn_date=datetime(2025, 12, 15), amount=Decimal("840")),
        Transaction(txn_id="6", txn_date=datetime(2026, 1, 15), amount=Decimal("840")),
    ]
    
    # Run discovery
    engine = DeterministicPatternDiscovery(transactions)
    candidates = engine.discover_patterns()
    
    print(f"\n✓ Discovered {len(candidates)} pattern(s)\n")
    
    for i, candidate in enumerate(candidates, 1):
        print(f"Pattern {i}:")
        print(f"  Case: {candidate.pattern_case.value}")
        print(f"  Interval: {candidate.interval_days} days")
        print(f"  Amount Behavior: {candidate.amount_behavior.value}")
        print(f"  Average Amount: ₹{candidate.cluster.avg_amount:.2f}")
        print(f"  Confidence: {candidate.confidence:.2%}")
        print(f"  Transactions: {len(candidate.transactions)}")
    
    return candidates


# ==============================================================================
# EXAMPLE 2: Generate LLM explanation
# ==============================================================================

def example_explain_pattern(candidate):
    """
    Example: Get LLM-generated explanation for a pattern.
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 2: Pattern Explanation (LLM)")
    print("=" * 80)
    
    agent = PatternExplanationAgent()
    
    explanation = agent.explain_pattern(
        transactor_name="Netflix",
        pattern_case=candidate.pattern_case,
        interval_days=candidate.interval_days,
        amount_behavior=candidate.amount_behavior,
        avg_amount=candidate.cluster.avg_amount,
        min_amount=candidate.cluster.min_amount,
        max_amount=candidate.cluster.max_amount,
        confidence=candidate.confidence,
        observation_count=len(candidate.transactions),
        currency_symbol="₹"
    )
    
    print(f"\n✓ Pattern Explanation:\n")
    print(f"  Display Name: {explanation['display_name']}")
    print(f"  Explanation: {explanation['explanation_text']}")
    print(f"  Confidence Reasoning: {explanation['confidence_reasoning']}")
    print(f"  Valid for Users: {explanation['is_valid']}")
    
    return explanation


# ==============================================================================
# EXAMPLE 3: Create pattern state and obligation
# ==============================================================================

def example_create_obligation(candidate):
    """
    Example: Create pattern state and compute next obligation.
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 3: Obligation Creation")
    print("=" * 80)
    
    # Create initial pattern state
    last_txn = candidate.transactions[-1]
    
    state = PatternObligationManager.create_initial_state(
        pattern_id="example-pattern-id",
        pattern_case=candidate.pattern_case,
        interval_days=candidate.interval_days,
        amount_behavior=candidate.amount_behavior,
        last_transaction_date=last_txn.txn_date,
        initial_confidence=candidate.confidence
    )
    
    print(f"\n✓ Pattern State Created:\n")
    print(f"  Status: {state.status}")
    print(f"  Last Actual Date: {state.last_actual_date.strftime('%Y-%m-%d')}")
    print(f"  Next Expected Date: {state.next_expected_date.strftime('%Y-%m-%d')}")
    print(f"  Current Streak: {state.current_streak}")
    print(f"  Confidence Multiplier: {state.confidence_multiplier:.2f}")
    
    # Estimate amount range for obligation
    recent_amounts = [t.amount for t in candidate.transactions[-3:]]
    min_amt, max_amt = PatternObligationManager.estimate_amount_range(
        recent_amounts,
        candidate.amount_behavior
    )
    
    # Create obligation
    obligation = PatternObligationManager.create_obligation(
        state=state,
        expected_min_amount=min_amt,
        expected_max_amount=max_amt
    )
    
    print(f"\n✓ Next Obligation Created:\n")
    print(f"  Expected Date: {obligation.expected_date.strftime('%Y-%m-%d')}")
    print(f"  Tolerance: ±{obligation.tolerance_days} days")
    print(f"  Expected Amount: ₹{min_amt:.2f} - ₹{max_amt:.2f}")
    print(f"  Status: {obligation.status.value}")
    
    return state, obligation


# ==============================================================================
# EXAMPLE 4: Process new transaction (obligation matching)
# ==============================================================================

def example_process_transaction(state):
    """
    Example: Process a new transaction against pattern state.
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 4: Transaction Processing")
    print("=" * 80)
    
    # Simulate new transaction arriving on time
    new_txn_date = datetime(2026, 2, 15)
    new_txn_amount = Decimal("840")
    
    print(f"\n→ New transaction: ₹{new_txn_amount} on {new_txn_date.strftime('%Y-%m-%d')}")
    
    # Check if it matches the obligation
    tolerance = PatternObligationManager.compute_tolerance_window(
        state.pattern_case,
        state.interval_days
    )
    
    is_match, days_early = PatternObligationManager.check_obligation_match(
        transaction_date=new_txn_date,
        expected_date=state.next_expected_date,
        tolerance_days=tolerance
    )
    
    if is_match:
        print(f"✓ Transaction matched! ({days_early:+.0f} days from expected)")
        
        # Fulfill obligation
        updated_state = PatternObligationManager.fulfill_obligation(
            state=state,
            actual_transaction_date=new_txn_date,
            days_early=days_early
        )
        
        print(f"\n✓ Pattern State Updated:\n")
        print(f"  Status: {updated_state.status}")
        print(f"  Current Streak: {updated_state.current_streak}")
        print(f"  Missed Count: {updated_state.missed_count}")
        print(f"  Confidence Multiplier: {updated_state.confidence_multiplier:.2f}")
        print(f"  Next Expected: {updated_state.next_expected_date.strftime('%Y-%m-%d')}")
        
        return updated_state
    else:
        print(f"✗ Transaction did not match (outside tolerance window)")
        return state


# ==============================================================================
# EXAMPLE 5: Handle missed obligation
# ==============================================================================

def example_handle_miss(state):
    """
    Example: Handle a missed obligation (safe degradation).
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 5: Missed Obligation Handling")
    print("=" * 80)
    
    # Simulate time passing without transaction
    current_date = datetime(2026, 3, 20)  # Well past expected date
    
    print(f"\n→ Current date: {current_date.strftime('%Y-%m-%d')}")
    print(f"→ Expected date was: {state.next_expected_date.strftime('%Y-%m-%d')}")
    
    tolerance = PatternObligationManager.compute_tolerance_window(
        state.pattern_case,
        state.interval_days
    )
    
    is_overdue = PatternObligationManager.is_obligation_overdue(
        state.next_expected_date,
        tolerance,
        current_date
    )
    
    if is_overdue:
        print(f"✗ Obligation is overdue (tolerance: ±{tolerance} days)")
        
        # Handle miss
        updated_state = PatternObligationManager.handle_missed_obligation(
            state=state,
            current_date=current_date
        )
        
        print(f"\n✓ Pattern State Updated (Degraded):\n")
        print(f"  Status: {updated_state.status}")
        print(f"  Missed Count: {updated_state.missed_count}")
        print(f"  Confidence Multiplier: {updated_state.confidence_multiplier:.2f}")
        print(f"  Next Expected: {updated_state.next_expected_date.strftime('%Y-%m-%d')}")
        
        return updated_state


# ==============================================================================
# RUN ALL EXAMPLES
# ==============================================================================

if __name__ == "__main__":
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "PATTERN ANALYSIS QUICK START" + " " * 30 + "║")
    print("╚" + "=" * 78 + "╝")
    
    try:
        # Example 1: Discover patterns
        candidates = example_discover_patterns()
        
        if candidates:
            candidate = candidates[0]
            
            # Example 2: Explain pattern
            explanation = example_explain_pattern(candidate)
            
            # Example 3: Create obligation
            state, obligation = example_create_obligation(candidate)
            
            # Example 4: Process transaction
            updated_state = example_process_transaction(state)
            
            # Example 5: Handle missed obligation
            final_state = example_handle_miss(updated_state)
            
            print("\n" + "=" * 80)
            print("✓ All examples completed successfully!")
            print("=" * 80 + "\n")
        else:
            print("\n✗ No patterns discovered. Try with more transaction data.\n")
            
    except Exception as e:
        print(f"\n✗ Error: {e}\n")
        import traceback
        traceback.print_exc()
