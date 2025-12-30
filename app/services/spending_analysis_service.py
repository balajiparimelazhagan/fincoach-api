
from app.models import SpendingAnalysisJob, RecurringPattern
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from uuid import uuid4

class SpendingAnalysisService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_job(self, user_id, triggered_by):
        job = SpendingAnalysisJob(
            id=uuid4(),
            user_id=user_id,
            status='PENDING',
            triggered_by=triggered_by,
            started_at=None,
            finished_at=None,
            error_message=None,
            error_log=[],
            celery_task_id=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            is_locked=True,
            locked_at=datetime.utcnow(),
        )
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def update_job_status(self, job_id, status, error_message=None, error_log=None):
        result = await self.db.execute(
            SpendingAnalysisJob.__table__.select().where(SpendingAnalysisJob.id == job_id)
        )
        job = result.fetchone()
        if job:
            # Ensure status is a string
            if hasattr(status, 'value'):
                status = status.value
            
            await self.db.execute(
                SpendingAnalysisJob.__table__.update()
                .where(SpendingAnalysisJob.id == job_id)
                .values(
                    status=status,
                    error_message=error_message,
                    updated_at=datetime.utcnow(),
                    finished_at=datetime.utcnow() if status in ('SUCCESS', 'FAILED') else None,
                    is_locked=False if status in ('SUCCESS', 'FAILED') else True,
                    error_log=error_log if error_log else job.error_log,
                )
            )
            await self.db.commit()
        return job

    async def fetch_transactions(self, user_id):
        # TODO: Implement actual transaction fetching logic
        return []

    async def persist_patterns(self, patterns):
        for pattern in patterns:
            self.db.add(pattern)
        await self.db.commit()

    async def get_job(self, job_id):
        result = await self.db.execute(
            SpendingAnalysisJob.__table__.select().where(SpendingAnalysisJob.id == job_id)
        )
        return result.fetchone()

    async def get_jobs(self, user_id):
        result = await self.db.execute(
            SpendingAnalysisJob.__table__.select().where(SpendingAnalysisJob.user_id == user_id)
        )
        return result.fetchall()
