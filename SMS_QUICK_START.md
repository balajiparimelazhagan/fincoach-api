# SMS Sync Quick Start Guide

## Prerequisites
- Docker and docker-compose installed
- Python 3.9+ with dependencies installed
- Database running

## Setup Steps

### 1. Run Database Migrations
```bash
cd api
alembic upgrade head
```

Expected output:
```
INFO  [alembic.runtime.migration] Running upgrade 014 -> 015, create user_permissions table
INFO  [alembic.runtime.migration] Running upgrade 015 -> 016, create sms_sync_jobs table
INFO  [alembic.runtime.migration] Running upgrade 016 -> 017, rename transaction_sync_jobs to email_transaction_sync_jobs
```

### 2. Start Services
```bash
# Option A: Using Docker Compose
docker-compose up -d

# Option B: Manual start
# Terminal 1 - API
uvicorn app.main:app --reload --port 8000

# Terminal 2 - Celery Worker
celery -A app.celery.celery_app worker --loglevel=info

# Terminal 3 - Celery Beat (optional, for scheduled tasks)
celery -A app.celery.celery_app beat --loglevel=info
```

### 3. Verify API is Running
```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "ok",
  "database": "connected"
}
```

## Testing the SMS Sync Flow

### Step 1: Create a Test User (if needed)
```bash
# Use existing user ID or create one via auth endpoints
USER_ID="your-user-uuid-here"
```

### Step 2: Grant SMS Permission
```bash
curl -X POST http://localhost:8000/api/v1/sms-sync/permission/$USER_ID/grant \
  -H "Content-Type: application/json" \
  -d '{"permission_type": "sms_read"}'
```

Expected response:
```json
{
  "message": "SMS permission granted successfully",
  "permission_id": "permission-uuid",
  "granted_at": "2025-12-06T10:30:00.000Z"
}
```

### Step 3: Check Permission Status
```bash
curl http://localhost:8000/api/v1/sms-sync/permission/$USER_ID/status
```

Expected response:
```json
{
  "has_permission": true,
  "status": "active",
  "granted_at": "2025-12-06T10:30:00.000Z",
  "permission_id": "permission-uuid"
}
```

### Step 4: Upload Test SMS Messages

#### Test Case 1: Loan Payment SMS
```bash
curl -X POST http://localhost:8000/api/v1/sms-sync/upload/$USER_ID \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {
        "sms_id": "sms_001",
        "body": "UPDATE: INR 26,200.00 debited from HDFC Bank XX4319 on 05-DEC-25. Info: ACH D- TP ACH PNBHOUSINGFIN-2030932846. Avl bal:INR 1,10,961.82",
        "sender": "HDFCBK",
        "timestamp": "2025-12-05T09:30:00Z"
      }
    ]
  }'
```

#### Test Case 2: Salary Credit SMS
```bash
curl -X POST http://localhost:8000/api/v1/sms-sync/upload/$USER_ID \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {
        "sms_id": "sms_002",
        "body": "Update! INR 1,31,506.00 deposited in HDFC Bank A/c XX4319 on 28-NOV-25 for Salary NOV 2025. Avl bal INR 1,53,427.37",
        "sender": "HDFCBK",
        "timestamp": "2025-11-28T08:00:00Z"
      }
    ]
  }'
```

#### Test Case 3: Multiple SMS Batch
```bash
curl -X POST http://localhost:8000/api/v1/sms-sync/upload/$USER_ID \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {
        "sms_id": "sms_003",
        "body": "INR 500.00 debited from A/c XX4319 via UPI to test@upi on 06-DEC-25. Ref: 123456789",
        "sender": "HDFCBK",
        "timestamp": "2025-12-06T10:00:00Z"
      },
      {
        "sms_id": "sms_004",
        "body": "INR 2,500.00 credited to A/c XX4319 from bonus payment on 06-DEC-25",
        "sender": "HDFCBK",
        "timestamp": "2025-12-06T11:00:00Z"
      }
    ]
  }'
```

Expected response:
```json
{
  "message": "SMS batch processing started",
  "task_id": "celery-task-id",
  "user_id": "user-uuid",
  "sms_count": 2
}
```

### Step 5: Check Processing Status
```bash
curl http://localhost:8000/api/v1/sms-sync/status/$USER_ID
```

Response (processing):
```json
{
  "job_id": "job-uuid",
  "status": "processing",
  "progress": 50.0,
  "total_sms": 2,
  "processed_sms": 1,
  "parsed_transactions": 1,
  "failed_sms": 0,
  "skipped_sms": 0,
  "started_at": "2025-12-06T10:00:00Z",
  "completed_at": null
}
```

Response (completed):
```json
{
  "job_id": "job-uuid",
  "status": "completed",
  "progress": 100.0,
  "total_sms": 2,
  "processed_sms": 2,
  "parsed_transactions": 2,
  "failed_sms": 0,
  "skipped_sms": 0,
  "started_at": "2025-12-06T10:00:00Z",
  "completed_at": "2025-12-06T10:00:15Z"
}
```

### Step 6: View Extracted Transactions
```bash
curl http://localhost:8000/api/v1/transactions?user_id=$USER_ID
```

You should see the extracted transactions with:
- Correct amounts
- Proper categories (Loan Payment, Salary, UPI Transfer)
- Transaction dates
- Transactor information

### Step 7: View Sync History
```bash
curl http://localhost:8000/api/v1/sms-sync/history/$USER_ID?limit=10
```

Expected response:
```json
{
  "user_id": "user-uuid",
  "total_jobs": 3,
  "jobs": [
    {
      "job_id": "latest-job-uuid",
      "status": "completed",
      "progress": 100.0,
      "total_sms": 2,
      "processed_sms": 2,
      "parsed_transactions": 2,
      "failed_sms": 0,
      "skipped_sms": 0,
      "started_at": "2025-12-06T10:00:00Z",
      "completed_at": "2025-12-06T10:00:15Z",
      "created_at": "2025-12-06T10:00:00Z"
    }
  ]
}
```

## Debugging

### Check Celery Logs
```bash
# If using Docker
docker-compose logs -f celery_worker

# If running manually, check the terminal where celery worker is running
```

Look for:
```
[A2A-SMS] Processing SMS sms_001
[A2A-SMS] Intent Classification: transaction (confidence: 0.95)
[A2A-SMS] Successfully extracted transaction: 26200.0 expense
✓ Committed SMS transaction: 26200.0 expense - UPDATE: INR 26,200.00 debited from HDFC Bank...
```

### Check Database
```sql
-- Check permissions
SELECT * FROM user_permissions WHERE user_id = 'user-uuid';

-- Check SMS sync jobs
SELECT * FROM sms_sync_jobs WHERE user_id = 'user-uuid' ORDER BY created_at DESC;

-- Check extracted transactions
SELECT * FROM transactions WHERE user_id = 'user-uuid' ORDER BY date DESC LIMIT 10;
```

### Common Issues

1. **Permission denied error**
   - Make sure you've granted SMS permission first
   - Check permission status endpoint

2. **No transactions extracted**
   - Check Celery worker logs for errors
   - Verify SMS format matches supported patterns
   - Check if messages are being skipped by intent classifier

3. **Database connection error**
   - Verify database is running: `docker-compose ps`
   - Check connection settings in `.env`

4. **Import errors**
   - Make sure all dependencies are installed: `pip install -r requirements.txt`
   - Check Python path includes the `api` directory

## Testing with Postman

Import this collection:

```json
{
  "info": {
    "name": "SMS Sync API",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "variable": [
    {
      "key": "base_url",
      "value": "http://localhost:8000/api/v1"
    },
    {
      "key": "user_id",
      "value": "your-user-uuid"
    }
  ],
  "item": [
    {
      "name": "Grant SMS Permission",
      "request": {
        "method": "POST",
        "url": "{{base_url}}/sms-sync/permission/{{user_id}}/grant",
        "body": {
          "mode": "raw",
          "raw": "{\"permission_type\": \"sms_read\"}"
        }
      }
    },
    {
      "name": "Upload SMS Batch",
      "request": {
        "method": "POST",
        "url": "{{base_url}}/sms-sync/upload/{{user_id}}",
        "body": {
          "mode": "raw",
          "raw": "{\"messages\": [{\"sms_id\": \"test_001\", \"body\": \"INR 26,200.00 debited from HDFC Bank XX4319 on 05-DEC-25\", \"sender\": \"HDFCBK\", \"timestamp\": \"2025-12-05T09:30:00Z\"}]}"
        }
      }
    },
    {
      "name": "Check Status",
      "request": {
        "method": "GET",
        "url": "{{base_url}}/sms-sync/status/{{user_id}}"
      }
    }
  ]
}
```

## Next Steps

1. **Add Authentication**: Secure all endpoints with JWT tokens
2. **Rate Limiting**: Prevent abuse with rate limits
3. **Mobile Integration**: Build Android/iOS apps to read and upload SMS
4. **Monitoring**: Set up alerts for failed jobs
5. **Analytics**: Track extraction success rates

## Support

For issues or questions:
1. Check logs: `docker-compose logs -f celery_worker`
2. Review documentation: `SMS_SYNC_DOCUMENTATION.md`
3. Check implementation summary: `SMS_IMPLEMENTATION_SUMMARY.md`
