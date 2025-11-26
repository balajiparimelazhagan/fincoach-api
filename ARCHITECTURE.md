# FinCoach Architecture Diagram

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Load Balancer                            │
│                     (Production Only)                            │
└────────────────────────┬────────────────────────────────────────┘
                         │
         ┌───────────────┴───────────────┐
         │                               │
    ┌────▼─────┐                   ┌────▼─────┐
    │ FastAPI  │                   │ FastAPI  │
    │  App 1   │                   │  App 2   │
    │ :8000    │                   │ :8000    │
    └────┬─────┘                   └────┬─────┘
         │                               │
         └───────────────┬───────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
    ┌────▼─────┐   ┌────▼─────┐   ┌────▼─────┐
    │  Redis   │   │PostgreSQL│   │  Celery  │
    │  Broker  │   │    DB    │   │  Beat    │
    │  :6379   │   │  :5432   │   │Scheduler │
    └────┬─────┘   └────┬─────┘   └────┬─────┘
         │               │               │
         └───────────────┴───────────────┘
                         │
         ┌───────────────┴───────────────┐
         │                               │
    ┌────▼─────┐                   ┌────▼─────┐
    │  Celery  │                   │  Celery  │
    │ Worker 1 │  ...              │ Worker N │
    │(4 tasks) │                   │(4 tasks) │
    └──────────┘                   └──────────┘
```

## Data Flow: Initial Email Sync

```
User Signs Up
     │
     ▼
┌─────────────────────────────────────────┐
│ POST /api/v1/email-sync/start/{user_id} │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│  Create Task in Redis Queue              │
│  fetch_user_emails_initial.delay()       │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│  Celery Worker Picks Up Task            │
│  (from celery_worker container)          │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│  1. Create EmailSyncJob (status=PENDING) │
│  2. Fetch emails from Gmail API          │
│  3. Process in batches of 100            │
└─────────────────┬───────────────────────┘
                  │
                  ▼
      ┌───────────┴───────────┐
      │                       │
      ▼                       ▼
┌──────────────┐    ┌──────────────────┐
│ Parse Email  │    │ Update Progress  │
│ with AI      │    │ in Database      │
└──────┬───────┘    └──────────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│ Save Transaction to PostgreSQL       │
│ - Get/Create Category                │
│ - Get/Create Transactor               │
│ - Create Transaction Record           │
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│ Update Job Status                    │
│ - processed_emails++                 │
│ - parsed_transactions++              │
│ - progress_percentage = %            │
└──────────────────┬───────────────────┘
                   │
                   ▼
         ┌─────────┴─────────┐
         │                   │
         ▼                   ▼
   More Emails?          Job Complete
         │                   │
         Yes                 ▼
         │           ┌───────────────┐
         └──────────►│ status=       │
                     │ COMPLETED     │
                     └───────────────┘
```

## Data Flow: Incremental Sync (Automatic)

```
Every 30 Minutes
     │
     ▼
┌─────────────────────────────────────┐
│ Celery Beat Triggers                │
│ schedule_incremental_sync()          │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│ Query All Users from Database       │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│ Create Task for Each User           │
│ fetch_user_emails_incremental.delay│
│ (Parallel Execution)                │
└─────────────────┬───────────────────┘
                  │
                  ▼
      ┌───────────┴───────────┐
      │                       │
      ▼                       ▼
┌──────────────┐    ┌──────────────┐
│ Worker 1:    │    │ Worker 2:    │
│ User A       │    │ User B       │
└──────┬───────┘    └──────┬───────┘
       │                   │
       └───────────┬───────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│ Fetch Only New Emails                │
│ since last_email_fetch_time          │
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│ Parse & Save Transactions            │
│ (Same flow as initial sync)          │
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│ Update last_email_fetch_time         │
└──────────────────────────────────────┘
```

## Component Responsibilities

### 1. FastAPI Application
- **Role**: REST API Server
- **Responsibilities**:
  - Handle HTTP requests
  - Authentication & Authorization
  - Queue tasks to Celery
  - Return job status to users
- **Port**: 8000
- **Scaling**: Horizontal (multiple instances)

### 2. PostgreSQL Database
- **Role**: Persistent Data Store
- **Responsibilities**:
  - Store users, transactions, categories
  - Track email sync jobs
  - Maintain referential integrity
- **Port**: 5432 (5434 external)
- **Scaling**: Vertical + Read Replicas

### 3. Redis
- **Role**: Message Broker & Result Backend
- **Responsibilities**:
  - Queue Celery tasks
  - Store task results
  - Provide pub/sub for workers
- **Port**: 6379
- **Scaling**: Redis Cluster or ElastiCache

### 4. Celery Workers
- **Role**: Background Task Processors
- **Responsibilities**:
  - Fetch emails from Gmail API
  - Parse emails with AI
  - Save transactions to database
  - Update job progress
- **Count**: 4 (configurable)
- **Concurrency**: 4 tasks per worker
- **Scaling**: Horizontal (add more workers)

### 5. Celery Beat
- **Role**: Periodic Task Scheduler
- **Responsibilities**:
  - Trigger incremental syncs every 30 minutes
  - Schedule maintenance tasks
  - Ensure periodic updates run
- **Count**: 1 (singleton)
- **Scaling**: No scaling (only 1 needed)

## Database Schema

```
┌─────────────┐         ┌──────────────┐
│    users    │         │ email_sync   │
│             │◄────────┤    jobs      │
│ id (PK)     │ 1     * │              │
│ email       │         │ user_id (FK) │
│ token       │         │ status       │
│ last_fetch  │         │ progress_%   │
└──────┬──────┘         └──────────────┘
       │
       │ 1
       │
       │ *
┌──────▼──────────┐
│  transactions   │
│                 │
│ id (PK)         │
│ user_id (FK)    │
│ category_id (FK)│
│ transactor_id   │
│ amount          │
│ type            │
│ date            │
│ message_id (UQ) │◄── Unique constraint
└─────────────────┘     prevents duplicates
```

## Task Queue Flow

```
API Request
    │
    ▼
┌────────────────┐
│ Redis Queue    │
│                │
│ Task 1 ────┐   │
│ Task 2 ────┤   │
│ Task 3 ────┤   │
│ Task 4 ────┤   │
│ Task 5 ────┤   │
└────────────┼───┘
             │
     ┌───────┴────────┐
     │                │
     ▼                ▼
┌─────────┐      ┌─────────┐
│Worker 1 │      │Worker 2 │
│         │      │         │
│Task 1   │      │Task 2   │
│Task 5   │      │Task 3   │
│         │      │Task 4   │
└─────────┘      └─────────┘
```

## Monitoring & Observability

```
┌─────────────────────────────────────────┐
│         Monitoring Dashboard             │
│  (CloudWatch / Datadog / Grafana)        │
└─────────┬───────────────────────────────┘
          │
    ┌─────┴─────┐
    │           │
    ▼           ▼
┌────────┐  ┌────────┐
│ Metrics│  │  Logs  │
└────┬───┘  └───┬────┘
     │          │
     │          ▼
     │    ┌──────────────┐
     │    │ Worker Logs  │
     │    │ API Logs     │
     │    │ Error Traces │
     │    └──────────────┘
     │
     ▼
┌──────────────────────┐
│ Key Metrics:         │
│ - Tasks/sec          │
│ - Queue length       │
│ - Success rate       │
│ - Avg processing time│
│ - Memory usage       │
│ - CPU usage          │
└──────────────────────┘
```

## Scaling Strategy

### Phase 1: 100 Users
```
1 API Instance
1 DB Instance
1 Redis Instance
2 Celery Workers
1 Celery Beat
```

### Phase 2: 1,000 Users
```
2 API Instances (Load Balanced)
1 DB Instance (RDS)
1 Redis Instance (ElastiCache)
4 Celery Workers
1 Celery Beat
```

### Phase 3: 10,000 Users
```
4 API Instances (Auto-Scaled)
1 DB Instance + Read Replicas
Redis Cluster
16 Celery Workers (Auto-Scaled)
1 Celery Beat
```

### Phase 4: 100,000+ Users
```
Auto-Scaled API (10-50 instances)
Multi-AZ RDS with Read Replicas
ElastiCache Cluster
Auto-Scaled Workers (50-200)
Celery Beat (HA setup)
```

## Deployment Architecture (AWS)

```
┌────────────────────────────────────────────────────────┐
│                    Route 53 (DNS)                       │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│              Application Load Balancer                  │
└───────────────────┬────────────────────────────────────┘
                    │
        ┌───────────┴───────────┐
        │                       │
        ▼                       ▼
┌───────────────┐       ┌───────────────┐
│  ECS Service  │       │  ECS Service  │
│  (API)        │       │  (API)        │
│  Fargate      │       │  Fargate      │
└───────────────┘       └───────────────┘
        │                       │
        └───────────┬───────────┘
                    │
        ┌───────────┼───────────┐
        │           │           │
        ▼           ▼           ▼
┌──────────┐  ┌──────────┐  ┌──────────┐
│   RDS    │  │ElastiCache│ │   ECS    │
│PostgreSQL│  │  Redis   │  │ Workers  │
│          │  │          │  │ (Celery) │
└──────────┘  └──────────┘  └──────────┘
```

---

**Created**: November 25, 2025
**Status**: ✅ Production Ready
**Version**: 1.0
