# A2A Communication Flow Diagram

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                   Email Processing Coordinator                   │
│                        (Orchestrator)                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ Email Input (subject, body)
                              ▼
        ┌─────────────────────────────────────────────────┐
        │         LAYER 1: Intent Classification           │
        │                                                  │
        │      ┌──────────────────────────────┐           │
        │      │  IntentClassifierAgent       │           │
        │      │  Model: Gemini 2.5 Flash     │           │
        │      └──────────────────────────────┘           │
        │                                                  │
        │  Classifies:                                     │
        │  • TRANSACTION (actual money movement)           │
        │  • PROMOTIONAL (offers, deals)                   │
        │  • INFORMATIONAL (statements, reminders)         │
        │  • UNKNOWN (unclear)                             │
        └─────────────────────────────────────────────────┘
                              │
                              │ IntentClassification
                              │ {intent, confidence, reasoning}
                              ▼
        ┌─────────────────────────────────────────────────┐
        │            DECISION LOGIC                        │
        │                                                  │
        │  If (intent == TRANSACTION && confidence > 0.7): │
        │      → Proceed to Layer 2                        │
        │  Else:                                           │
        │      → Skip extraction                           │
        │      → Log skip reason                           │
        │      → Increment skipped_emails                  │
        └─────────────────────────────────────────────────┘
                              │
                              │ Approved for extraction
                              ▼
        ┌─────────────────────────────────────────────────┐
        │         LAYER 2: Transaction Extraction          │
        │                                                  │
        │      ┌──────────────────────────────┐           │
        │      │ TransactionExtractorAgent    │           │
        │      │ Model: Gemini 2.5 Flash      │           │
        │      │ + Regex Fallback             │           │
        │      └──────────────────────────────┘           │
        │                                                  │
        │  Extracts:                                       │
        │  • Amount                                        │
        │  • Type (income/expense)                         │
        │  • Date & Time                                   │
        │  • Category                                      │
        │  • Description                                   │
        │  • Transactor                                    │
        │  • Transactor Source ID                          │
        └─────────────────────────────────────────────────┘
                              │
                              │ Transaction Object
                              ▼
        ┌─────────────────────────────────────────────────┐
        │              DATABASE STORAGE                    │
        │                                                  │
        │  • Save transaction                              │
        │  • Link to transactor                            │
        │  • Update job metrics                            │
        │  • Log success                                   │
        └─────────────────────────────────────────────────┘
```

## Communication Protocol

### Request Flow
```
Celery Worker
    │
    ├─► Initialize EmailProcessingCoordinator
    │       │
    │       ├─► Create IntentClassifierAgent
    │       └─► Create TransactionExtractorAgent
    │
    └─► For each email:
            │
            ├─► coordinator.process_email(msg_id, subject, body)
            │       │
            │       ├─► [A2A Step 1] intent_classifier.classify_email()
            │       │       └─► Returns: IntentClassification
            │       │
            │       ├─► [A2A Step 2] Coordinator evaluates result
            │       │       ├─► If not transaction → Skip
            │       │       └─► If transaction + high confidence → Continue
            │       │
            │       └─► [A2A Step 3] extractor.parse_email()
            │               └─► Returns: Transaction | None
            │
            └─► Process result:
                    ├─► If processed → Save to DB
                    └─► If skipped → Log reason
```

## Data Structures

### IntentClassification
```python
{
    "intent": "transaction" | "promotional" | "informational" | "unknown",
    "confidence": 0.0 - 1.0,
    "reasoning": "Brief explanation",
    "should_extract": true | false
}
```

### EmailProcessingResult
```python
{
    "intent_classification": IntentClassification,
    "transaction": Transaction | None,
    "processed": bool,
    "skip_reason": str | None
}
```

### Transaction
```python
{
    "amount": float,
    "transaction_type": "income" | "expense",
    "date": datetime,
    "category": str,
    "description": str,
    "transactor": str,
    "transactor_source_id": str | None,
    "confidence": float,
    "message_id": str
}
```

## Example Scenarios

### Scenario 1: Actual Transaction (Happy Path)
```
Input: "You've spent Rs. 300 via UPI to AMUTHA K"

[A2A Step 1] Intent Classifier
    → intent: "transaction"
    → confidence: 0.98
    → reasoning: "UPI debit transaction completed"
    → should_extract: true

[A2A Step 2] Coordinator Decision
    ✓ Intent is transaction
    ✓ Confidence > 0.7
    → Proceed to extraction

[A2A Step 3] Transaction Extractor
    → amount: 300.0
    → type: "expense"
    → transactor: "AMUTHA K"
    → Success!

Result: Transaction saved ✓
```

### Scenario 2: Promotional Email (Filtered)
```
Input: "Offer: Get Rs.350 Voucher + Cashback!"

[A2A Step 1] Intent Classifier
    → intent: "promotional"
    → confidence: 0.95
    → reasoning: "Voucher and cashback offer"
    → should_extract: false

[A2A Step 2] Coordinator Decision
    ✗ Intent is not transaction
    → Skip extraction

Result: Email skipped, reason logged ✓
```

### Scenario 3: Payment Reminder (Filtered)
```
Input: "Payment Reminder: Rs. 5,432 due on 15-Dec"

[A2A Step 1] Intent Classifier
    → intent: "informational"
    → confidence: 0.92
    → reasoning: "Payment due reminder, not completed"
    → should_extract: false

[A2A Step 2] Coordinator Decision
    ✗ Intent is not transaction
    → Skip extraction

Result: Email skipped, reason logged ✓
```

## Performance Characteristics

### Latency
- Intent Classification: ~1-2 seconds (Gemini 2.5 Flash)
- Transaction Extraction: ~1-2 seconds (when invoked)
- Total (happy path): ~2-4 seconds
- Total (filtered): ~1-2 seconds (no extraction)

### Throughput
- Batch processing: 100 emails per batch
- Parallel workers: Configurable (default: 4)
- Expected filtering rate: 30-40% (promotional/informational)

### Accuracy (Target)
- Intent Classification: >95% accuracy
- Transaction Extraction: >90% accuracy (for approved emails)
- False Positives: <5% (promos classified as transactions)
- False Negatives: <3% (transactions classified as promos)

## Monitoring & Observability

### Key Logs
```
[A2A] Processing email {message_id}
[A2A] Step 1: Invoking Intent Classifier Agent
[A2A] Intent Classification: {intent} (confidence: {conf})
[A2A] Reasoning: {reasoning}
[A2A] Step 2: Skipping extraction - {reason}
[A2A] Step 2: Approved for extraction, invoking Transaction Extractor Agent
[A2A] Step 3: Successfully extracted transaction: {amount} {type}
```

### Metrics Dashboard
```
┌─────────────────────────────────────────┐
│        Email Processing Metrics          │
├─────────────────────────────────────────┤
│ Total Emails:           1,250           │
│ Processed (Transactions): 780  (62%)    │
│ Skipped (Filtered):       420  (34%)    │
│   - Promotional:          280           │
│   - Informational:        140           │
│ Failed (Errors):           50  (4%)     │
├─────────────────────────────────────────┤
│ Intent Classification                    │
│   Transaction:            850  (68%)    │
│   Promotional:            280  (22%)    │
│   Informational:          140  (11%)    │
│   Unknown:                 30  (2%)     │
└─────────────────────────────────────────┘
```
