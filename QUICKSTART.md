# Quick Start Guide

## Prerequisites
- Docker & Docker Compose installed
- Git installed

## Setup Steps

### 1. Clone/Navigate to Project
```bash
cd c:\Users\balaji\Desktop\fincoach
```

### 2. Create .env File (if not exists)
```bash
# Create .env file with necessary configuration
DATABASE_URL=postgresql://postgres:root@db/postgres
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
GOOGLE_API_KEY=your-api-key-here
JWT_SECRET_KEY=your-secret-key-here
```

### 3. Build and Start Services
```bash
docker-compose up --build
```

This will start:
- ✅ PostgreSQL database
- ✅ Redis message broker
- ✅ FastAPI application
- ✅ 4 Celery workers
- ✅ Celery Beat scheduler

### 4. Run Database Migrations
In a new terminal:
```bash
docker-compose exec api alembic upgrade head
```

### 5. Verify Services

**Check API:**
```bash
curl http://localhost:8000/health
```

**Check Celery Workers:**
```bash
docker-compose logs celery_worker --tail=50
```

**Check Celery Beat:**
```bash
docker-compose logs celery_beat --tail=50
```

**Check Redis:**
```bash
docker exec -it fincoach-redis-1 redis-cli ping
# Should return: PONG
```

## Test Email Sync

### Option 1: Via API (Recommended)

1. Get a user ID from your database
2. Trigger sync:
```bash
curl -X POST "http://localhost:8000/api/v1/email-sync/start/{user_id}?months=1"
```

3. Check progress:
```bash
curl "http://localhost:8000/api/v1/email-sync/status/{user_id}"
```

### Option 2: Via Test Script
```bash
docker-compose exec api python test_celery_task.py
```

## Monitor Progress

### Watch Worker Logs
```bash
docker-compose logs celery_worker -f
```

### Check Job Status in Database
```bash
docker-compose exec db psql -U postgres -d postgres -c "SELECT id, user_id, status, progress_percentage, parsed_transactions FROM email_sync_jobs ORDER BY created_at DESC LIMIT 5;"
```

### View API Documentation
Open browser: http://localhost:8000/docs

## Troubleshooting

### Workers Not Starting
```bash
# Check Redis connection
docker-compose logs redis

# Restart workers
docker-compose restart celery_worker
```

### Database Connection Issues
```bash
# Check DB logs
docker-compose logs db

# Verify connection
docker-compose exec api python -c "from app.db import database; import asyncio; asyncio.run(database.connect()); print('DB Connected!')"
```

### Tasks Not Processing
```bash
# Check Redis queue
docker exec -it fincoach-redis-1 redis-cli LLEN celery

# Purge queue (if needed)
docker exec -it fincoach-redis-1 redis-cli FLUSHDB
```

## Scaling

### Scale Workers Horizontally
```bash
# Run 8 workers instead of 4
docker-compose up --scale celery_worker=8
```

### Scale Workers Vertically
Edit `docker-compose.yml`:
```yaml
celery_worker:
  entrypoint: ["/usr/app/celery_worker_entrypoint.sh"]
  # Add this environment variable
  environment:
    - CELERY_CONCURRENCY=8  # 8 concurrent tasks per worker
```

## Stop Services
```bash
docker-compose down
```

## Clean Restart
```bash
# Stop and remove all containers, volumes
docker-compose down -v

# Rebuild and start
docker-compose up --build
```

## Production Deployment

For production deployment, see `EMAIL_PROCESSING_GUIDE.md` section on "Production Deployment".

Key considerations:
- Use managed Redis (AWS ElastiCache)
- Use managed PostgreSQL (AWS RDS)
- Deploy workers on ECS/Fargate with auto-scaling
- Set up CloudWatch monitoring
- Configure proper retry policies
- Enable Sentry for error tracking

## Next Steps

1. ✅ Start services
2. ✅ Run migrations
3. ✅ Test with one user
4. ✅ Monitor worker logs
5. ✅ Scale as needed
6. 🔜 Implement AI spend analysis
7. 🔜 Build forecasting models

## Support

- Full documentation: `EMAIL_PROCESSING_GUIDE.md`
- Implementation details: `IMPLEMENTATION_SUMMARY.md`
- API docs: http://localhost:8000/docs
