# Pattern System Workflow Documentation

## Overview
This document explains how the recurring pattern detection and obligation tracking system works.

## Core Architecture Principles

### Transaction Immutability
- **Transactions are immutable facts** once persisted to the database
- Never deleted or modified during pattern processing
- Pattern links never alter transaction data
- Discovery and matching are read-only operations on transaction history

### Two-Phase Pattern System

#### 1. Discovery Phase (On-Demand)
- Triggered explicitly via `POST /patterns/analyze`
- Analyzes **unassigned transaction history** to find recurring patterns
- Filters out transactions already linked to patterns via `pattern_transactions`
- Creates new patterns with initial obligations
- Uses deterministic algorithm (Steps 0-9, no ML/LLM)
- LLM only generates explanations AFTER pattern creation

#### 2. Real-Time Matching Phase (Per Transaction)
- Triggered automatically on each new transaction ingestion
- **ONLY matches against existing active patterns**
- **NO pattern discovery** during real-time processing
- Performs lazy miss detection (checks for overdue obligations)
- Updates pattern state, fulfills obligations, creates next expected obligation
- Fast, O(active_patterns) complexity

### Key Behavioral Details

#### Miss Detection (Lazy Evaluation)
- Misses are NOT detected immediately on expected_date
- Detection happens during next transaction processing
- If user stops transacting, misses won't be detected until next transaction
- Pattern state updates only when new transaction arrives

#### Amount Matching
- **Date matching is PRIMARY**: Transaction date must fall within expected_date ± tolerance_days
- **Amount matching is NOT enforced** in current implementation
- Amount range (expected_min_amount, expected_max_amount) stored for forecasting only
- Any amount accepted if date matches

#### Pattern Updates
- Re-running discovery on same (transactor, direction, currency) updates existing pattern
- Pattern updated in-place (not deleted and recreated)
- `detection_version` incremented to track re-analysis
- Transaction links preserved
- Prevents pattern ID changes that would break references

## Database Tables

### recurring_patterns
- Stores discovered recurring payment patterns
- One row per unique pattern (e.g., Netflix monthly subscription)
- Fields: user_id, transactor_id, direction, pattern_type, interval_days, amount_behavior, status, confidence
- Status can be: ACTIVE, PAUSED, or BROKEN
- Confidence is a score from 0.0 to 1.0 indicating pattern reliability

### pattern_transactions
- Links transactions to patterns (many-to-many relationship)
- One row per transaction-pattern link
- Fields: recurring_pattern_id, transaction_id, linked_at
- Append-only table (never delete links once created)
- Prevents re-analysis by tracking which transactions belong to which patterns

### pattern_obligations
- Tracks expected future payments
- One row per expected payment
- Fields: recurring_pattern_id, expected_date, tolerance_days, expected_min_amount, expected_max_amount, status
- Status can be: EXPECTED, FULFILLED, MISSED, or CANCELLED
- Updated when transactions match the expected payment
- Stores fulfillment details: fulfilled_by_transaction_id, fulfilled_at, days_early

### recurring_pattern_streaks
- Tracks pattern health and payment consistency
- One-to-one relationship with recurring_patterns
- Fields: current_streak_count, longest_streak_count, last_actual_date, last_expected_date, missed_count, confidence_multiplier
- Updated on every transaction that matches the pattern
- High write frequency table (separated from patterns table for performance)

## Pattern Discovery Flow

### Trigger
- Admin or user calls: POST /patterns/analyze
- Can filter by transactor_id or direction
- Runs deterministic analysis on historical transactions

### Step 1: Group Transactions
- File: api/app/services/pattern_service.py
- Function: _get_transaction_groups() [line 99]
- Groups transactions by: (user_id, transactor_id, direction, currency_id)
- Only considers groups with MIN_TRANSACTIONS_REQUIRED (1) or more
- Returns list of groups to analyze

### Step 2: Discover Patterns Per Group
- File: api/app/services/pattern_service.py
- Function: _discover_patterns_for_group() [line 160]
- Fetches all transactions for the group, sorted by date
- **Filters out already-linked transactions** (checks `pattern_transactions` table)
- Only analyzes unassigned transactions to prevent re-analysis
- Logs: total transactions, linked count, unassigned count
- Converts unassigned transactions to DiscoveryTransaction format (txn_id, txn_date, amount)
- Calls pattern discovery engine

### Step 3: Run Deterministic Discovery Algorithm
- File: api/agent/pattern_discovery_engine.py
- Function: discover_patterns() [line 427]
- Implements Steps 0-9 from requirements document
- No ML, no LLM, pure deterministic logic
- **Effective minimum: 3 transactions** (need 2+ gaps for interval detection)
- Steps:
  - Step 0: Validate inputs (min 1 transaction required by constant, but 3 needed in practice)
  - Step 1: Compute intervals between consecutive transactions
  - Step 2: Remove "too frequent" intervals (< 10 days or > 3 per 30 days)
  - Step 3: Detect stable interval (mean, median, standard deviation)
  - Step 4: Classify pattern case (MONTHLY, BI_MONTHLY, QUARTERLY, etc.)
  - Step 5: Cluster amounts by similarity
  - Step 6: Filter outliers and noise
  - Step 7: Compute amount behavior (FIXED, VARIABLE, HIGHLY_VARIABLE)
  - Step 8: Calculate confidence score (0.0 to 1.0)
  - Step 9: Return PatternCandidate objects
- Returns list of discovered patterns

### Step 4: Get LLM Explanation
- File: api/app/services/pattern_service.py
- Function: _discover_patterns_for_group() [line 230]
- Calls PatternExplanationAgent.explain_pattern()
- Uses currency symbol from CURRENCY_SYMBOLS constant (api/agent/regex_constants.py)
- LLM only judges and explains, never computes
- LLM can mark pattern as invalid if it doesn't make sense
- Returns human-readable explanation for UI
- Includes transactor object in result dict to avoid SQLAlchemy lazy loading issues

### Step 5: Save Pattern to Database
- File: api/app/services/pattern_service.py
- Function: _save_pattern() [line 272]
- Check if pattern already exists (by user_id, transactor_id, direction)
- If exists: update with new values, increment detection_version
- If new: create new recurring_patterns row
- Flush to get pattern ID
- After commit, refresh pattern with transactor relationship loaded to prevent lazy loading errors

### Step 6: Create or Update Streak
- File: api/app/services/pattern_service.py
- Function: _save_pattern() [line 320]
- Check if streak record exists
- If new: create recurring_pattern_streaks row with **INITIAL values**
  - **This is INITIALIZATION, not runtime update**
  - Same table updated later during runtime matching
  - Two different operations on same table: initialize once, update many times
- Set current_streak_count = number of transactions found
- Set longest_streak_count = same
- Set last_actual_date = most recent transaction date
- Set missed_count = 0
- Set confidence_multiplier = 1.0

### Step 7: Link Transactions to Pattern
- File: api/app/services/pattern_service.py
- Function: _save_pattern() [line 351]
- For each transaction in the discovered pattern:
  - Check if pattern_transactions link already exists
  - If not: create new pattern_transactions row
  - Links transaction to pattern permanently

### Step 8: Create Initial Obligation
- File: api/app/services/pattern_service.py
- Function: _create_next_obligation() [line 388]
- Calls PatternObligationManager.create_initial_state() from api/agent/pattern_obligation_manager.py
- Computes next expected payment date (last_date + interval_days)
- Computes tolerance window (±3 days for MONTHLY)
- Estimates amount range (min/max based on history)
- Uses PatternObligationManager.create_obligation_from_state() to create obligation object
- Creates pattern_obligations row with status=EXPECTED
- Commit all changes to database

## Real-Time Transaction Processing Flow

**CRITICAL: This flow NEVER creates new recurring_patterns. Patterns only created via POST /patterns/analyze.**

### Trigger
- New transaction is created (from SMS, Email, or Manual entry)
- Transaction is saved to database
- handle_new_transaction() is called
- **Only matching and state updates happen - NO discovery**

### Step 1: Queue Async Task
- File: api/app/services/transaction_handler.py
- Function: handle_new_transaction() [line 14]
- Queues Celery task: update_recurring_streak.delay()
- Passes: user_id, transactor_id, direction, transaction_date
- Returns immediately (non-blocking)

### Step 2: Celery Worker Processes Task
- File: api/app/celery/celery_tasks.py
- Function: update_recurring_streak() [line 35]
- Celery worker picks up the task
- Calls PatternService.process_new_transaction()
- Passes transaction_id

### Step 3: Find Matching Patterns
- File: api/app/services/pattern_service.py
- Function: process_new_transaction() [line 548]
- Fetch the transaction from database
- Query active patterns for this (user, transactor, direction)
- Only considers patterns with status = ACTIVE or PAUSED
- **Note:** This is real-time matching ONLY, NO discovery happens here
- Returns empty if no patterns found

### Step 4: Match Against Each Pattern (with Lazy Miss Detection)
- File: api/app/services/pattern_service.py
- Function: process_new_transaction() [line 613]
- For each active pattern:
  - Load pattern state (from pattern + streak records)
  - Create PatternState object
  - Call TransactionProcessor.process_transaction() from api/agent/pattern_obligation_manager.py
  - **Processor checks for overdue obligations FIRST** (lazy miss detection)
  - If obligation overdue: calls handle_missed_obligation()
  - Then checks if transaction date falls within expected window (±tolerance_days)
  - **Amount is NOT checked** - any amount accepted if date matches
  - Returns (updated_state, was_matched) tuple

### Step 5: Apply State Updates (If Matched)
- File: api/app/services/pattern_service.py
- Function: _apply_state_update() [line 611]
- **CRITICAL: NO new recurring_patterns created here - only state updates**
- Update recurring_pattern_streaks:
  - **This is UPDATE, not initialization** (same table as discovery, different operation)
  - Increment current_streak_count
  - Update longest_streak_count if needed
  - Set last_actual_date = transaction date
  - Set last_expected_date = obligation expected date
  - Update confidence_multiplier (stays at 1.0 if no misses)
- Update recurring_patterns (existing row):
  - Set status = from updated state
  - Set last_evaluated_at = now
  - **Pattern row already exists from discovery** - just updating fields
- Find pending obligation (status=EXPECTED)
- Update pattern_obligations:
  - Set status = FULFILLED
  - Set fulfilled_by_transaction_id = transaction.id
  - Set fulfilled_at = transaction.date
  - Set days_early = (expected_date - actual_date).days
- Create pattern_transactions link:
  - Link transaction to pattern (new link, not new pattern)
- Create next obligation:
  - Call _create_next_obligation_from_state()
  - Estimate amount range from recent 3 transactions
  - Compute next expected date (current + interval_days)
  - Create new pattern_obligations row with status=EXPECTED

### Step 6: Commit Changes
- File: api/app/services/pattern_service.py
- Function: process_new_transaction() [line 587]
- Commit all database changes
- Return match results

## Obligation Tracking Logic

### Initial Obligation Creation
- Happens after pattern discovery
- Function: _create_next_obligation() in pattern_service.py [line 344]
- Uses PatternObligationManager.create_initial_state()
- Inputs: pattern details, last transaction date
- Outputs: next expected date, tolerance window

### Tolerance Window Calculation
- File: api/agent/pattern_obligation_manager.py
- Different for each pattern type:
  - DAILY: ±1 day
  - WEEKLY: ±2 days
  - MONTHLY: ±3 days
  - QUARTERLY: ±7 days
- Pattern case affects tolerance:
  - FIXED_MONTHLY: strict tolerance
  - VARIABLE_MONTHLY: looser tolerance
  - FLEXIBLE_MONTHLY: very loose tolerance

### Amount Range Estimation
- File: api/agent/pattern_obligation_manager.py
- Function: estimate_amount_range()
- Based on recent transaction amounts (last 3)
- Different logic for each amount behavior:
  - FIXED: tight range (mean ± 5%)
  - VARIABLE: moderate range (mean ± 25%)
  - HIGHLY_VARIABLE: wide range (min to max of history)

### Transaction Matching
- File: api/agent/pattern_obligation_manager.py
- Function: match_transaction() (implied in TransactionProcessor.process_transaction)
- Checks:
  - Is transaction date within tolerance window?
  - Is amount within expected range?
  - Both must be true for a match

### Obligation Fulfillment
- When transaction matches:
  - Mark obligation as FULFILLED
  - Record which transaction fulfilled it
  - Record fulfillment date
  - Calculate how early/late (days_early)
  - Create next obligation

### Miss Detection
- Happens when:
  - Current date > (expected_date + tolerance_days)
  - Obligation still has status = EXPECTED
- **Detection Timing (Lazy Evaluation):**
  - Checked during real-time transaction processing (TransactionProcessor)
  - NOT checked proactively on expected_date
  - If user stops transacting, pattern stays in old state indefinitely
  - Miss only detected when next transaction arrives for that (transactor, direction)
- Updates:
  - Mark obligation as MISSED
  - Increment missed_count in streak
  - Reset current_streak_count = 0
  - Decrease confidence_multiplier
  - May change pattern status to PAUSED or BROKEN
- **Implementation:** api/agent/pattern_obligation_manager.py
  - is_obligation_overdue() checks if current_date > expected_date + tolerance
  - handle_missed_obligation() applies state degradation

## Pattern State Transitions

### ACTIVE
- Pattern is functioning normally
- Payments are being made on time
- Confidence is maintained or increasing

### PAUSED
- Pattern has missed some payments
- Not completely broken yet
- System still tracks and can resume to ACTIVE
- **Happens when: 1 < missed_count ≤ 3** (MAX_MISSED_FOR_PAUSED = 3)

### BROKEN
- Pattern has failed consistently
- Multiple missed payments
- Confidence very low
- **Happens when: missed_count > 3** (MAX_MISSED_FOR_PAUSED exceeded)
- Pattern is kept in database but not actively tracked
- Never deleted automatically (preserves history)

### Recovery (PAUSED/BROKEN → ACTIVE)
- Can happen if:
  - User makes a payment that matches expected window
  - System detects pattern resumption
  - Streak rebuilds
  - Confidence increases above threshold

## API Endpoints

### POST /patterns/analyze
- File: api/app/routes/patterns.py [line 197]
- Trigger pattern discovery
- Optional filters: transactor_id, direction
- Returns: list of discovered patterns with explanations
- Admin only (requires authentication)

### GET /patterns
- File: api/app/routes/patterns.py [line 73]
- Get all patterns for authenticated user
- Optional filter: status (ACTIVE, PAUSED, BROKEN)
- Optional: include_obligations (default true)
- Returns: patterns with transactor info, streak info, obligations

### GET /patterns/{pattern_id}
- File: api/app/routes/patterns.py [line 95]
- Get specific pattern details
- Returns: full pattern with obligations and metrics

### GET /patterns/{pattern_id}/obligations
- File: api/app/routes/patterns.py [line 124]
- Get obligations for specific pattern
- Optional filter: status
- Optional: limit (default 10)
- Returns: list of obligations sorted by date

### GET /patterns/obligations/upcoming
- File: api/app/routes/patterns.py [line 159]
- Get all upcoming obligations for user
- Optional: days_ahead (default 30)
- Returns: obligations due within next N days
- Includes: pattern info, transactor info, expected amounts

### PUT /patterns/{pattern_id}
- File: api/app/routes/patterns.py [line 233]
- Update pattern (pause/resume, adjust settings)
- Returns: updated pattern

### DELETE /patterns/{pattern_id}
- File: api/app/routes/patterns.py [line 281]
- Delete pattern
- Also deletes: streak, obligations, transaction links
- Soft delete (can be recovered if needed)

## Key Files and Components

### Pattern Discovery
- api/agent/pattern_discovery_engine.py
  - DeterministicPatternDiscovery class
  - discover_patterns() method [line 427]
  - Steps 0-9 implementation
  - Pure deterministic logic, no ML/LLM

### Obligation Management
- api/agent/pattern_obligation_manager.py
  - PatternObligationManager class
  - PatternState dataclass
  - TransactionProcessor class
  - create_initial_state() method
  - match_transaction() logic
  - Steps 10-15 implementation

### Service Layer
- api/app/services/pattern_service.py
  - PatternService class
  - Orchestrates discovery and updates
  - discover_patterns_for_user() [line 51]
  - process_new_transaction() [line 488]
  - All database operations

### API Routes
- api/app/routes/patterns.py
  - All REST endpoints
  - Request/response schemas
  - Authentication checks

### Background Tasks
- api/app/celery/celery_tasks.py
  - update_recurring_streak() [line 35]
  - Async processing of transactions
  - Queued via transaction_handler.py

### Transaction Handler
- api/app/services/transaction_handler.py
  - handle_new_transaction() [line 14]
  - Entry point for new transactions
  - Queues pattern processing

## Data Flow Summary

### Discovery Flow
1. User/Admin → POST /patterns/analyze
2. API Route → PatternService.discover_patterns_for_user()
3. Service → Group transactions by (user, transactor, direction, currency)
4. Service → For each group, call _discover_patterns_for_group()
5. Service → DeterministicPatternDiscovery.discover_patterns()
6. Engine → Run Steps 0-9, return PatternCandidate
7. Service → PatternExplanationAgent.explain_pattern()
8. Service → _save_pattern() saves to database
9. Database → recurring_patterns + recurring_pattern_streaks + pattern_transactions + pattern_obligations
10. API Route → Return discovered patterns to user

### Real-Time Flow
1. Transaction Created → handle_new_transaction()
2. Handler → Queue update_recurring_streak.delay()
3. Celery Worker → PatternService.process_new_transaction()
4. Service → Find active patterns for transaction
5. Service → For each pattern, check if transaction matches
6. Service → TransactionProcessor.process_transaction()
7. Processor → Check date within window, amount within range
8. Service → If match: _apply_state_update()
9. Service → Update streak, fulfill obligation, link transaction, create next obligation
10. Database → All tables updated with new state

## Important Principles

### Deterministic Only
- Pattern discovery uses ONLY deterministic logic
- No machine learning, no predictions
- No LLM involvement in computation
- LLM only judges and explains after computation

### State-Based Tracking
- Never recompute from full history
- Each pattern has current state
- Updates are incremental
- Fast lookups without rescanning all transactions

### Currency Isolation
- Patterns are per-currency
- Never mix transactions in different currencies
- Each (user, transactor, direction, currency) is separate group

### Multiple Patterns Per Transactor
- One transactor can have multiple patterns
- Example: Mutual Fund with ₹1000 SIP and ₹500 SIP
- Amount clustering distinguishes them

### Safe Degradation
- Patterns transition: ACTIVE → PAUSED → BROKEN
- Never deleted (preserves history)
- Can recover from PAUSED/BROKEN
- Confidence degrades gradually

### Append-Only Links
- pattern_transactions links are never deleted
- Once linked, always linked
- Prevents re-analysis bugs
- Clean audit trail

## Configuration Constants

### Pattern Discovery (pattern_discovery_engine.py)
- MIN_TRANSACTIONS_REQUIRED = 1 (but effective minimum is 3 for gap computation)
- FREQUENT_THRESHOLD_PER_30_DAYS = 3
- AMOUNT_TOLERANCE_PERCENT = 0.25 (25%)
- AMOUNT_TOLERANCE_ABSOLUTE = ₹50
- MIN_INTERVAL_DAYS = 10
- MONTHLY_RANGE = (27, 33) days
- BI_MONTHLY_RANGE = (55, 65) days
- QUARTERLY_RANGE = (85, 95) days
- CV_FIXED_THRESHOLD = 0.05
- CV_VARIABLE_THRESHOLD = 0.30

### Currency Constants (regex_constants.py)
- CURRENCY_SYMBOLS: Maps currency codes to symbols (INR→₹, USD→$, EUR→€, GBP→£, JPY→¥, AUD→A$, CAD→C$, CHF→CHF, CNY→¥)

### Obligation Tolerance (pattern_obligation_manager.py)
- DAILY: ±1 day
- WEEKLY: ±2 days
- MONTHLY: ±3 days
- QUARTERLY: ±7 days

### Pattern State Transitions (pattern_obligation_manager.py)
- MAX_MISSED_FOR_ACTIVE = 1 (missed_count ≤ 1 keeps pattern ACTIVE)
- MAX_MISSED_FOR_PAUSED = 3 (1 < missed_count ≤ 3 moves to PAUSED)
- CONFIDENCE_DECAY_PER_MISS = 0.15
- CONFIDENCE_BOOST_PER_FULFILL = 0.05

## Testing the System

### Manual Pattern Discovery
1. Ensure user has 3+ transactions with same transactor
2. Call POST /patterns/analyze with auth token
3. Check response for discovered patterns
4. Verify database: recurring_patterns, recurring_pattern_streaks, pattern_transactions, pattern_obligations

### Automatic Transaction Processing
1. Create new transaction (via SMS, Email, or API)
2. Wait for Celery worker to process
3. Check pattern_obligations: should be FULFILLED
4. Check recurring_pattern_streaks: streak should increment
5. Check new obligation created for next period

### Viewing Patterns
1. Call GET /patterns to see all user patterns
2. Call GET /patterns/{id} for specific pattern details
3. Call GET /patterns/obligations/upcoming for upcoming payments

### Pattern Health
1. Miss a payment (don't create transaction in expected window)
2. System should mark obligation as MISSED
3. Pattern confidence should decrease
4. After 3 misses, pattern status → BROKEN

## Table Fill Order (Authoritative)

This is the **strict, immutable order** in which database tables are populated.

### Discovery Phase (On-Demand: POST /patterns/analyze)

```
1. transactions (already exists - immutable source of truth)
    ↓
2. recurring_patterns (created FIRST - defines the pattern)
    ↓ await self.db.flush()
3. recurring_pattern_streaks (INITIALIZED - first values set)
    ↓ await self.db.flush()
4. pattern_transactions (links created - makes pattern traceable)
    ↓
5. pattern_obligations (first obligation created - enables tracking)
    ↓ await self.db.commit()
```

**Critical Rules:**
- `recurring_patterns` is created ONLY during discovery
- `recurring_pattern_streaks` is initialized with first values (current_streak=1, missed_count=0)
- This phase NEVER happens during real-time transaction processing

### Real-Time Phase (Per Transaction)

```
1. transactions (insert - new transaction arrives)
    ↓
2. [matching only - NO new patterns created]
    ↓
3. pattern_obligations (UPDATED - status=FULFILLED or MISSED)
    ↓
4. recurring_pattern_streaks (UPDATED - counters incremented/decremented)
    ↓ await self.db.commit()
```

**Critical Rules:**
- `recurring_patterns` is NEVER created here (only updated: status, last_evaluated_at)
- `recurring_pattern_streaks` is UPDATED (current_streak++, longest_streak, confidence_multiplier)
- Same table, different operation: initialized once (discovery), updated many times (runtime)
- New `pattern_transactions` links created if match found
- New `pattern_obligations` row created for next expected occurrence

### Optional/Async Phase

```
budget_forecasts (NOT YET IMPLEMENTED)
- Depends on existing recurring_patterns + current state
- Can be regenerated at any time
- Never blocks pattern creation or updates
```

### Hard Invariants

| Rule | Enforcement |
|------|-------------|
| **No `recurring_patterns` during runtime** | Only `POST /patterns/analyze` creates patterns |
| **No table before its dependency** | Flush after each dependency satisfied |
| **`transactions` always first** | Pattern logic never blocks transaction insert |
| **`recurring_pattern_streaks` two modes** | Initialize (discovery) vs Update (runtime) |
| **Pattern links are append-only** | `pattern_transactions` never deleted |

### State Diagram

```
[Transaction Insert]
        ↓
  Is Pattern Discovery
   Trigger Active?
        ↓
    NO  |  YES
        |   ↓
        |  [Discovery Phase]
        |   ├── Create recurring_patterns
        |   ├── Initialize recurring_pattern_streaks  ← FIRST TIME
        |   ├── Link pattern_transactions
        |   └── Create pattern_obligations
        ↓
   [Real-Time Phase]
   ├── Match against existing patterns
   ├── Update pattern_obligations
   └── Update recurring_pattern_streaks  ← MANY TIMES
```

### Implementation Evidence

**Discovery Phase** (`api/app/services/pattern_service.py` - `_save_pattern()`):
- Line 326-345: Create `recurring_patterns` row
- Line 346: `await self.db.flush()` (get pattern ID)
- Line 348-367: Create `recurring_pattern_streaks` row (INITIALIZE)
- Line 373-387: Create `pattern_transactions` links
- Line 390: Call `_create_next_obligation()` (line 403)
- Line 397: `await self.db.commit()`

**Real-Time Phase** (`api/app/services/pattern_service.py` - `_apply_state_update()`):
- Line 632-638: UPDATE `recurring_pattern_streaks` (current_streak++, confidence, etc.)
- Line 641-642: UPDATE `recurring_patterns` (status, last_evaluated_at)
- Line 645-653: UPDATE `pattern_obligations` (status=FULFILLED)
- Line 656-662: CREATE new `pattern_transactions` link
- Line 665: CREATE next `pattern_obligations` row
- Line 675: `await self.db.commit()`
- **NO creation of `recurring_patterns`** - only updates!
