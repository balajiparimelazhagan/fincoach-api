# FinCoach Email Processing Setup Guide

## Architecture Overview

The system now uses a **distributed task queue architecture** with Celery workers for scalable email processing:

```
FastAPI (API)  →  Redis (Broker)  →  Celery Workers (Email Processing)
     ↓                                        ↓
PostgreSQL ←────────────────────────────────┘
     ↑
Celery Beat (Scheduler - runs every 30 min)
```

## Components

1. **FastAPI API** - REST API for user requests
2. **PostgreSQL** - Database for transactions and job tracking
3. **Redis** - Message broker and result backend for Celery
4. **Celery Workers** - Process email fetch/parse tasks asynchronously
5. **Celery Beat** - Periodic scheduler for incremental syncs

## Getting Started

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run Database Migrations

```bash
alembic upgrade head
```

### 3. Start All Services with Docker Compose

```bash
docker-compose up --build
```

This starts:
- **API** on `http://localhost:8000`
- **PostgreSQL** on `localhost:5434`
- **Redis** on `localhost:6379`
- **4 Celery Workers** for email processing
- **Celery Beat** for scheduling

## API Endpoints

### Start Email Sync for a User

```bash
POST /api/v1/email-sync/start/{user_id}?months=6
```

**Response:**
```json
{
  "message": "Email sync started",
  "task_id": "abc-123-def",
  "user_id": "user-uuid",
  "months": 6
}
```

### Check Sync Status

```bash
GET /api/v1/email-sync/status/{user_id}
```

**Response:**
```json
{
  "job_id": "job-uuid",
  "status": "processing",
  "progress": 45.5,
  "total_emails": 1500,
  "processed_emails": 683,
  "parsed_transactions": 612,
  "failed_emails": 71,
  "started_at": "2024-11-25T10:30:00",
  "completed_at": null
}
```

### View Sync History

```bash
GET /api/v1/email-sync/history/{user_id}?limit=10
```

### Get Overall Statistics

```bash
GET /api/v1/email-sync/stats
```

## How It Works

### Initial User Onboarding (Bulk Import)

1. User signs up and connects Gmail
2. API triggers: `fetch_user_emails_initial.delay(user_id, months=6)`
3. Celery worker picks up the task
4. Worker fetches emails in **batches of 100**
5. Each batch is parsed and saved to DB
6. Progress is tracked in `email_sync_jobs` table
7. User can check progress via API

### Incremental Sync (Automatic)

1. **Celery Beat** runs every 30 minutes
2. Triggers `schedule_incremental_sync` task
3. Creates a task for each user: `fetch_user_emails_incremental.delay(user_id)`
4. Workers fetch only **new emails** since `last_email_fetch_time`
5. Parses and saves new transactions

## Performance Characteristics

### For 1000 Users with 1500 Emails Each (1.5M emails)

- **4 Workers** processing 100 emails/batch
- **~30 seconds** per batch (fetch + parse + save)
- **Total time: ~5-6 hours** for initial sync
- **Scales horizontally** - add more workers to speed up

### Resource Usage

- Each worker: ~200-500MB RAM
- Redis: ~100MB RAM
- PostgreSQL: Variable based on transaction count

## Monitoring

### Check Celery Worker Status

```bash
docker-compose logs celery_worker -f
```

### Check Celery Beat Schedule

```bash
docker-compose logs celery_beat -f
```

### Check Redis Queue

```bash
docker exec -it fincoach-redis-1 redis-cli
> LLEN celery
> KEYS *
```

### Check Database Jobs

```sql
SELECT status, COUNT(*) 
FROM email_sync_jobs 
GROUP BY status;
```

## Scaling

### Horizontal Scaling (More Workers)

```bash
docker-compose up --scale celery_worker=8
```

This creates 8 worker instances for faster processing.

### Vertical Scaling (More Concurrency)

Edit `docker-compose.yml`:

```yaml
celery_worker:
  command: celery -A app.celery_app worker --loglevel=info --concurrency=8
```

## Troubleshooting

### Workers Not Processing Tasks

1. Check Redis connection:
   ```bash
   docker-compose logs redis
   ```

2. Restart workers:
   ```bash
   docker-compose restart celery_worker
   ```

### Tasks Failing

1. Check worker logs:
   ```bash
   docker-compose logs celery_worker -f
   ```

2. Check job error logs via API:
   ```bash
   GET /api/v1/email-sync/status/{user_id}
   ```

### High Memory Usage

1. Reduce batch size in `app/workers/email_tasks.py`:
   ```python
   BATCH_SIZE = 50  # Reduce from 100
   ```

2. Reduce worker concurrency in `docker-compose.yml`:
   ```yaml
   command: celery -A app.celery_app worker --concurrency=2
   ```

## Development

### Run Workers Locally (Without Docker)

```bash
# Terminal 1 - Start Redis
docker run -p 6379:6379 redis:7-alpine

# Terminal 2 - Start Worker
celery -A app.celery_app worker --loglevel=info

# Terminal 3 - Start Beat (scheduler)
celery -A app.celery_app beat --loglevel=info

# Terminal 4 - Start API
uvicorn app.main:app --reload
```

### Test a Task Manually

```python
from app.workers.email_tasks import fetch_user_emails_initial

# Synchronous call (blocking)
result = fetch_user_emails_initial(user_id="your-user-id", months=1)

# Async call (non-blocking)
task = fetch_user_emails_initial.delay(user_id="your-user-id", months=1)
print(task.id)  # Task ID
```

## Configuration

All settings in `app/config.py`:

```python
CELERY_BROKER_URL = "redis://redis:6379/0"
CELERY_RESULT_BACKEND = "redis://redis:6379/0"
EMAIL_FETCH_DAYS = 180  # Max lookback for incremental sync
```

## Database Schema

### New Table: `email_sync_jobs`

Tracks email fetch jobs:

```sql
CREATE TABLE email_sync_jobs (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    status VARCHAR(20) NOT NULL,  -- pending, processing, completed, failed
    total_emails INT DEFAULT 0,
    processed_emails INT DEFAULT 0,
    parsed_transactions INT DEFAULT 0,
    failed_emails INT DEFAULT 0,
    progress_percentage FLOAT DEFAULT 0.0,
    error_log JSONB DEFAULT '[]',
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### Updated: `transactions`

Added unique constraint:

```sql
ALTER TABLE transactions 
ADD CONSTRAINT uq_transactions_message_id 
UNIQUE (message_id);
```

This prevents duplicate processing of the same email.

## Production Deployment

### AWS/Cloud Setup

1. **RDS PostgreSQL** for database
2. **ElastiCache Redis** for broker/backend
3. **ECS/Fargate** for API and workers
4. **CloudWatch** for monitoring

### Environment Variables

```bash
DATABASE_URL=postgresql://user:pass@rds-endpoint/db
CELERY_BROKER_URL=redis://elasticache-endpoint:6379/0
CELERY_RESULT_BACKEND=redis://elasticache-endpoint:6379/0
```

### Health Checks

- API: `GET /health`
- Workers: Check Celery logs
- Redis: `redis-cli ping`
- Database: `SELECT 1`

## Next Steps

1. ✅ Email sync is now asynchronous and scalable
2. ✅ Progress tracking available via API
3. ✅ Automatic incremental syncs every 30 minutes
4. 🔜 Add AI spend analysis on transaction data
5. 🔜 Implement transaction categorization improvements
6. 🔜 Add forecasting models for next month predictions
