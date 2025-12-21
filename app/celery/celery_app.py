"""
Celery application configuration for distributed task processing.
"""
from celery import Celery
from celery.schedules import crontab

from app.config import settings

# Initialize Celery app
celery_app = Celery(
    'fincoach',
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=['app.celery.celery_tasks']  # Import task modules
)

# Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max per task
    task_soft_time_limit=3300,  # Soft limit at 55 minutes
    worker_prefetch_multiplier=1,  # Fetch one task at a time
    worker_max_tasks_per_child=50,  # Restart worker after 50 tasks (prevent memory leaks)
    broker_connection_retry_on_startup=True,
    result_expires=3600,  # Results expire after 1 hour
)

# Celery Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    'incremental-email-sync': {
        'task': 'app.celery.celery_tasks.schedule_incremental_sync',
        'schedule': crontab(minute='*/2'),  # Every 30 minutes
    },
}

# Task routes (optional - for routing specific tasks to specific queues)
celery_app.conf.task_routes = {
    'app.celery.celery_tasks.fetch_user_emails_initial': {'queue': 'email_processing'},
    'app.celery.celery_tasks.process_monthly_email_job': {'queue': 'email_processing'},
    'app.celery.celery_tasks.fetch_user_emails_incremental': {'queue': 'email_processing'},
    'app.celery.celery_tasks.schedule_incremental_sync': {'queue': 'scheduling'},
}
