# Multi-Agent Email Processing System

## Overview

This system implements a sophisticated multi-agent architecture using Google ADK (Agent Development Kit) to process financial emails intelligently. It uses **Agent-to-Agent (A2A) Communication** to coordinate between specialized agents, ensuring that only actual transaction emails are processed while filtering out promotional and informational content.

## Architecture

### Agent Hierarchy

```
EmailProcessingCoordinator (Orchestrator)
    ├── IntentClassifierAgent (Layer 1: Intent Detection)
    │   └── Determines: Transaction | Promotional | Informational | Unknown
    │
    └── TransactionExtractorAgent (Layer 2: Data Extraction)
        └── Extracts: Amount, Type, Date, Category, Description, Transactor
```

### Communication Flow

```
Email Input
    ↓
[Intent Classifier Agent]
    ↓
Intent Classification Result
    ↓
[Coordinator Decision Logic]
    ↓
Should Extract? (Yes/No)
    ↓
    Yes → [Transaction Extractor Agent] → Transaction Data
    No  → Skip (Log reason)
```

## Components

### 1. IntentClassifierAgent

**Purpose**: First-layer filter that determines the primary intent of an email.

**Input**:
- Email subject
- Email body (first 1000 characters)

**Output**:
- Intent type: `transaction`, `promotional`, `informational`, or `unknown`
- Confidence score: 0.0 to 1.0
- Reasoning: Explanation for the classification
- Should extract: Boolean decision

**Classification Rules**:
- **TRANSACTION**: Completed financial transactions with specific amounts
  - Keywords: "debited", "credited", "paid", "transferred", "transaction successful"
  - Must have: Completion status + specific amount

- **PROMOTIONAL**: Marketing and offers
  - Keywords: "offer", "cashback", "voucher", "discount", "sale", "limited time"
  - Focus: Encouraging future purchases

- **INFORMATIONAL**: Account updates without completed transactions
  - Keywords: "statement", "reminder", "due", "update", "summary"
  - Focus: Account status or pending actions

- **UNKNOWN**: Cannot determine with confidence

**Threshold**: Only proceeds to extraction if `intent = transaction` AND `confidence > 0.7`

### 2. TransactionExtractorAgent

**Purpose**: Second-layer agent that extracts structured transaction data from confirmed transactional emails.

**Input**:
- Message ID
- Email subject
- Email body

**Output**:
- Transaction object with:
  - Amount (float)
  - Transaction type (income/expense)
  - Date & time
  - Category
  - Description
  - Transactor name
  - Transactor source ID (UPI ID/account number)
  - Confidence score

**Extraction Methods**:
1. **AI-based**: Google Gemini 2.5 Flash model
2. **Regex fallback**: Pattern matching for UPI, bank transactions

### 3. EmailProcessingCoordinator

**Purpose**: Orchestrates A2A communication between agents and implements decision logic.

**Workflow**:
1. **Step 1**: Invoke Intent Classifier Agent
2. **Step 2**: Evaluate classification result
   - If not transactional: Skip extraction, log reason
   - If transactional + high confidence: Proceed to Step 3
3. **Step 3**: Invoke Transaction Extractor Agent
4. **Return**: Processing result with classification and optional transaction

**Logging**: Detailed A2A communication logs prefixed with `[A2A]`

## Integration

### Celery Tasks

The system is integrated into the email processing pipeline via `celery_tasks.py`:

```python
from agent.coordinator import EmailProcessingCoordinator

# Initialize coordinator
coordinator = EmailProcessingCoordinator()

# Process email batch
for email in emails:
    result = coordinator.process_email(message_id, subject, body)
    
    if result.processed:
        # Save transaction to database
        save_transaction(result.transaction)
    else:
        # Log skip reason
        job.skipped_emails += 1
        logger.info(f"Skipped: {result.skip_reason}")
```

### Database Schema

New field added to `transaction_sync_jobs` table:
- `skipped_emails`: Integer count of emails filtered by intent classifier

Migration: `014_add_skipped_emails_column.py`

## Benefits

### 1. Accuracy
- **False Positive Reduction**: Promotional emails no longer treated as transactions
- **Precision**: Two-layer validation ensures only actual transactions are extracted
- **Confidence Thresholding**: Low-confidence classifications are rejected

### 2. Efficiency
- **Early Rejection**: Non-transactional emails filtered before expensive extraction
- **Resource Optimization**: Transaction extractor only runs when necessary
- **Batch Processing**: Maintains high throughput with intelligent filtering

### 3. Observability
- **Detailed Logging**: A2A communication fully traced
- **Skip Reasons**: Clear explanations for rejected emails
- **Metrics**: Separate tracking of processed, skipped, and failed emails

### 4. Maintainability
- **Separation of Concerns**: Each agent has single responsibility
- **Modular Design**: Agents can be improved independently
- **Clear Interfaces**: Defined input/output contracts

## Example Results

### Promotional Email (Correctly Filtered)
```
Subject: "Offer: Festive Treats Rs.350 Voucher"
Intent: promotional (confidence: 0.95)
Reasoning: "Email offers voucher and cashback, promotional content"
Should Extract: false
Skipped: ✓
```

### Transaction Email (Correctly Extracted)
```
Subject: "You've spent Rs. 300.00 via UPI"
Intent: transaction (confidence: 0.98)
Reasoning: "Email confirms completed UPI debit transaction"
Should Extract: true
Extracted: ✓ Rs. 300.00 expense
```

### Informational Email (Correctly Filtered)
```
Subject: "Payment Reminder"
Intent: informational (confidence: 0.92)
Reasoning: "Payment due date reminder, no completed transaction"
Should Extract: false
Skipped: ✓
```

## Testing

Run the test suite:
```bash
docker-compose exec api python test_agent_coordination.py
```

This tests:
- Intent classification accuracy
- Extraction decision correctness
- False positive/negative rates
- End-to-end A2A coordination

## Configuration

### Environment Variables
- `GOOGLE_API_KEY`: Required for Google ADK agents
- All existing email processing settings

### Model Configuration
Both agents use `gemini-2.5-flash` for optimal balance of speed and accuracy.

## Monitoring

### Key Metrics
- `total_emails`: Total emails fetched
- `processed_emails`: Successfully processed transactions
- `skipped_emails`: Filtered by intent classifier (NEW)
- `failed_emails`: Extraction failures

### Log Prefixes
- `[A2A]`: Agent-to-Agent communication events
- Intent classification results logged at INFO level
- Extraction decisions logged with reasoning

## Future Enhancements

1. **Adaptive Learning**: Fine-tune intent classifier with user feedback
2. **Multi-Language Support**: Extend to non-English emails
3. **Custom Intent Types**: Allow user-defined intent categories
4. **A2A Metrics**: Track agent performance separately
5. **Parallel Processing**: Distribute intent classification across workers

## Migration Guide

### Applying Changes

1. Run migration:
```bash
docker-compose exec api alembic upgrade head
```

2. Restart services:
```bash
docker-compose restart
```

3. Verify:
```bash
docker-compose logs -f celery_worker
# Look for [A2A] logs
```

### Rollback

To revert to previous system:
```bash
docker-compose exec api alembic downgrade 013
```

Then update `celery_tasks.py` to use `TransactionExtractorAgent` directly.

## Troubleshooting

### Issue: High skip rate
- Check intent classifier logs for reasoning
- May need to adjust confidence threshold (currently 0.7)

### Issue: Transactions being skipped
- Verify email content has clear transaction indicators
- Check confidence scores in logs
- May need to retrain/adjust intent classifier instructions

### Issue: Promotional emails still processed
- Review intent classification reasoning
- May need to enhance promotional keywords
- Check if confidence threshold is too low

## References

- Google ADK Documentation: https://ai.google.dev/adk
- Agent-to-Agent Communication Patterns
- Multi-Agent System Design Principles
