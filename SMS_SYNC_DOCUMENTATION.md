# SMS Transaction Sync System

## Overview

The SMS Transaction Sync system enables mobile apps (Android/iOS) to read device SMS messages and extract financial transactions (like loan payments, salary credits, etc.) automatically. This complements the existing email transaction sync system.

## Architecture

### Components

1. **User Permission Management**
   - Model: `UserPermission` (`app/models/user_permission.py`)
   - Stores user consent for SMS/email reading
   - Permission types: `SMS_READ`, `EMAIL_READ`, `NOTIFICATION`
   - Tracks granted/revoked timestamps

2. **SMS Sync Job Tracking**
   - Model: `SmsSyncJob` (`app/models/sms_sync_job.py`)
   - Tracks SMS processing progress similar to email sync
   - Stores: total_sms, processed_sms, parsed_transactions, failed_sms, skipped_sms

3. **SMS Transaction Extractor Agent**
   - Agent: `SmsTransactionExtractorAgent` (`agent/sms_transaction_extractor.py`)
   - Extracts transaction data from SMS messages
   - Supports Indian bank SMS patterns (HDFC, PNB Housing Finance, etc.)
   - Categories: Loan Payment, Salary, Bills, UPI Transfer, etc.

4. **SMS Processing Coordinator**
   - Coordinator: `SmsProcessingCoordinator` (`agent/coordinator.py`)
   - Implements Agent-to-Agent (A2A) communication
   - Flow: Intent Classifier → Decision Logic → SMS Transaction Extractor

5. **API Endpoints**
   - Routes: `app/routes/sms_sync.py`
   - Prefix: `/api/v1/sms-sync`

6. **Background Processing**
   - Celery Task: `process_sms_batch_task` (`app/celery/celery_tasks.py`)
   - Processes SMS messages asynchronously

## API Endpoints

### 1. Grant SMS Permission
```
POST /api/v1/sms-sync/permission/{user_id}/grant
```

Request Body:
```json
{
  "permission_type": "sms_read"
}
```

Response:
```json
{
  "message": "SMS permission granted successfully",
  "permission_id": "uuid",
  "granted_at": "2025-12-06T10:30:00Z"
}
```

### 2. Revoke SMS Permission
```
POST /api/v1/sms-sync/permission/{user_id}/revoke
```

Response:
```json
{
  "message": "SMS permission revoked successfully",
  "permission_id": "uuid",
  "revoked_at": "2025-12-06T11:00:00Z"
}
```

### 3. Check Permission Status
```
GET /api/v1/sms-sync/permission/{user_id}/status
```

Response:
```json
{
  "has_permission": true,
  "status": "active",
  "granted_at": "2025-12-06T10:30:00Z",
  "permission_id": "uuid"
}
```

### 4. Upload SMS Batch
```
POST /api/v1/sms-sync/upload/{user_id}
```

Request Body:
```json
{
  "messages": [
    {
      "sms_id": "12345",
      "body": "INR 26,200.00 debited from HDFC Bank XX4319 on 05-DEC-25...",
      "sender": "HDFCBK",
      "timestamp": "2025-12-05T09:30:00Z",
      "thread_id": "thread_123"
    }
  ]
}
```

Response:
```json
{
  "message": "SMS batch processing started",
  "task_id": "celery-task-id",
  "user_id": "user-uuid",
  "sms_count": 50
}
```

### 5. Get Sync Status
```
GET /api/v1/sms-sync/status/{user_id}
```

Response:
```json
{
  "job_id": "job-uuid",
  "status": "processing",
  "progress": 65.5,
  "total_sms": 100,
  "processed_sms": 65,
  "parsed_transactions": 45,
  "failed_sms": 5,
  "skipped_sms": 15,
  "started_at": "2025-12-06T10:00:00Z",
  "completed_at": null
}
```

### 6. Get Sync History
```
GET /api/v1/sms-sync/history/{user_id}?limit=10
```

Response:
```json
{
  "user_id": "user-uuid",
  "total_jobs": 3,
  "jobs": [
    {
      "job_id": "job-uuid",
      "status": "completed",
      "progress": 100.0,
      "total_sms": 100,
      "processed_sms": 100,
      "parsed_transactions": 75,
      "failed_sms": 10,
      "skipped_sms": 15,
      "started_at": "2025-12-06T10:00:00Z",
      "completed_at": "2025-12-06T10:05:00Z",
      "created_at": "2025-12-06T10:00:00Z"
    }
  ]
}
```

## Mobile App Integration

### Android Implementation Example

```kotlin
// 1. Request SMS Permission
ActivityCompat.requestPermissions(
    this,
    arrayOf(Manifest.permission.READ_SMS),
    SMS_PERMISSION_REQUEST_CODE
)

// 2. Grant permission via API
suspend fun grantSmsPermission(userId: String) {
    api.post("/sms-sync/permission/$userId/grant") {
        body = PermissionRequest("sms_read")
    }
}

// 3. Read SMS messages
fun readSmsMessages(): List<SmsMessage> {
    val messages = mutableListOf<SmsMessage>()
    val cursor = contentResolver.query(
        Uri.parse("content://sms/inbox"),
        null, null, null, null
    )
    
    cursor?.use {
        while (it.moveToNext()) {
            val id = it.getString(it.getColumnIndexOrThrow("_id"))
            val address = it.getString(it.getColumnIndexOrThrow("address"))
            val body = it.getString(it.getColumnIndexOrThrow("body"))
            val date = it.getLong(it.getColumnIndexOrThrow("date"))
            
            // Filter bank SMS only
            if (isBankSms(address)) {
                messages.add(SmsMessage(
                    sms_id = id,
                    sender = address,
                    body = body,
                    timestamp = Instant.ofEpochMilli(date).toString()
                ))
            }
        }
    }
    return messages
}

// 4. Upload SMS batch
suspend fun uploadSmsBatch(userId: String, messages: List<SmsMessage>) {
    api.post("/sms-sync/upload/$userId") {
        body = SmsBatchRequest(messages)
    }
}

// 5. Check sync status
suspend fun checkSyncStatus(userId: String): SyncStatus {
    return api.get("/sms-sync/status/$userId")
}
```

### iOS Implementation Example

```swift
// Note: iOS doesn't allow direct SMS reading for privacy reasons
// Alternative: Use iMessage/WhatsApp business APIs or manual forwarding
```

## Supported SMS Patterns

### 1. Loan/EMI Payment
```
PAYMENT ALERT!
INR 26200.00 deducted from HDFC Bank A/C No 4319 towards PNB Housing Finance Limited UMRN: HDFC7021807230034209

UPDATE: INR 26,200.00 debited from HDFC Bank XX4319 on 05-DEC-25. Info: ACH D- TP ACH PNBHOUSINGFIN-2030932846. Avl bal:INR 1,10,961.82
```

**Extracted:**
- Amount: 26200.00
- Type: expense
- Category: Loan Payment
- Transactor: PNB Housing Finance
- Date: 2025-12-05

### 2. Salary Credit
```
Update! INR 1,31,506.00 deposited in HDFC Bank A/c XX4319 on 28-NOV-25 for Salary NOV 2025.Avl bal INR 1,53,427.37. Cheque deposits in A/C are subject to clearing
```

**Extracted:**
- Amount: 131506.00
- Type: income
- Category: Salary
- Description: Salary for NOV 2025
- Date: 2025-11-28

### 3. UPI Transfer
```
Rs.500 debited from A/c XX1234 via UPI to example@upi on 06-Dec-25. UPI Ref: 123456789
```

**Extracted:**
- Amount: 500.00
- Type: expense
- Category: UPI Transfer
- Transactor: example@upi

## Database Schema

### user_permissions
```sql
CREATE TABLE user_permissions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    permission_type ENUM('sms_read', 'email_read', 'notification'),
    granted_at TIMESTAMP NOT NULL,
    revoked_at TIMESTAMP,
    is_active VARCHAR NOT NULL DEFAULT 'True',
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE INDEX ix_user_permissions_user_id ON user_permissions(user_id);
CREATE INDEX ix_user_permissions_permission_type ON user_permissions(permission_type);
```

### sms_sync_jobs
```sql
CREATE TABLE sms_sync_jobs (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    status ENUM('pending', 'processing', 'completed', 'failed', 'paused'),
    total_sms INTEGER DEFAULT 0,
    processed_sms INTEGER DEFAULT 0,
    parsed_transactions INTEGER DEFAULT 0,
    failed_sms INTEGER DEFAULT 0,
    skipped_sms INTEGER DEFAULT 0,
    progress_percentage FLOAT DEFAULT 0.0,
    error_log JSONB DEFAULT '[]',
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE INDEX ix_sms_sync_jobs_user_id ON sms_sync_jobs(user_id);
CREATE INDEX ix_sms_sync_jobs_status ON sms_sync_jobs(status);
```

## Migration from Email-Only System

### Changes Made

1. **Renamed Models**
   - `TransactionSyncJob` → `EmailTransactionSyncJob`
   - Table: `transaction_sync_jobs` → `email_transaction_sync_jobs`

2. **Updated References**
   - `app/models/transaction_sync_job.py`
   - `app/routes/transaction_sync.py`
   - `app/celery/celery_tasks.py`

3. **New Models Added**
   - `UserPermission` (generic permission management)
   - `SmsSyncJob` (SMS-specific sync tracking)

4. **New Agents**
   - `SmsTransactionExtractorAgent`
   - `SmsProcessingCoordinator`

## Running Migrations

```bash
# Navigate to API directory
cd api

# Run migrations
alembic upgrade head

# This will run:
# - 015_create_user_permissions_table
# - 016_create_sms_sync_jobs_table
# - 017_rename_to_email_transaction_sync_jobs
```

## Testing

### Test SMS Permission Flow
```bash
# 1. Grant permission
curl -X POST http://localhost:8000/api/v1/sms-sync/permission/{user_id}/grant \
  -H "Content-Type: application/json" \
  -d '{"permission_type": "sms_read"}'

# 2. Check status
curl http://localhost:8000/api/v1/sms-sync/permission/{user_id}/status

# 3. Upload SMS batch
curl -X POST http://localhost:8000/api/v1/sms-sync/upload/{user_id} \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {
        "sms_id": "12345",
        "body": "INR 26,200.00 debited from HDFC Bank XX4319 on 05-DEC-25. Info: ACH D- TP ACH PNBHOUSINGFIN",
        "sender": "HDFCBK",
        "timestamp": "2025-12-05T09:30:00Z"
      }
    ]
  }'

# 4. Check sync status
curl http://localhost:8000/api/v1/sms-sync/status/{user_id}
```

## Security Considerations

1. **Permission Management**
   - Always verify permission before processing SMS
   - Allow users to revoke permission anytime
   - Log all permission grants/revocations

2. **Data Privacy**
   - Don't store raw SMS content
   - Only extract and store transaction data
   - Delete processed SMS data after extraction

3. **Authentication**
   - Ensure all endpoints require proper authentication
   - Validate user_id matches authenticated user
   - Use API tokens for mobile apps

4. **Rate Limiting**
   - Limit SMS upload batch size (e.g., max 1000 per request)
   - Implement rate limiting per user
   - Monitor for abuse

## Future Enhancements

1. **Real-time SMS Processing**
   - Mobile app sends SMS immediately upon receipt
   - WebSocket connection for real-time updates

2. **SMS Categorization ML Model**
   - Train custom model for better category prediction
   - Improve transactor identification

3. **Multi-bank Support**
   - Add bank-specific SMS parsers
   - Support international bank formats

4. **SMS Deduplication**
   - Detect duplicate SMS from same transaction
   - Merge information from multiple SMS

5. **Email Permission in Same Table**
   - Migrate email permission to `user_permissions` table
   - Unified permission management UI
