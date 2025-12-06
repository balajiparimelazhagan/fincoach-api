"""
SMS Transaction Sync API endpoints for SMS permission management and SMS batch processing.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel
from uuid import UUID

from app.db import get_db_session
from app.models.user_permission import UserPermission, PermissionType
from app.models.sms_transaction_sync_job import SmsTransactionSyncJob, JobStatus
from app.models.user import User
from app.celery.celery_tasks import process_sms_batch_task
from app.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/sms-transaction-sync", tags=["SMS Transaction Sync"])


# Pydantic models for request/response
class SmsMessage(BaseModel):
    """Single SMS message from mobile device"""
    sms_id: str  # Unique ID from device (e.g., _id from Android SMS ContentProvider)
    body: str
    sender: str  # Short code or phone number
    timestamp: datetime  # When SMS was received
    thread_id: Optional[str] = None


class SmsBatchRequest(BaseModel):
    """Batch of SMS messages from mobile app"""
    messages: List[SmsMessage]


class PermissionRequest(BaseModel):
    """Request to grant or revoke permission"""
    permission_type: str = "sms_read"


@router.post("/permission/{user_id}/grant")
async def grant_sms_transaction_permission(
    user_id: str,
    request: PermissionRequest = Body(...),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Grant SMS read permission for a user.
    Called by mobile app after user grants SMS permission.
    
    Args:
        user_id: User ID
        request: Permission request with type
    
    Returns:
        Permission grant confirmation
    """
    # Validate user exists
    user = (await session.execute(select(User).filter_by(id=user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if permission already exists and is active
    existing_permission = (await session.execute(
        select(UserPermission)
        .filter_by(
            user_id=user_id, 
            permission_type=PermissionType.SMS_READ
        )
        .filter(UserPermission.revoked_at.is_(None))
    )).scalar_one_or_none()
    
    if existing_permission:
        return {
            "message": "SMS transaction permission already granted",
            "permission_id": str(existing_permission.id),
            "granted_at": existing_permission.granted_at.isoformat()
        }
    
    # Create new permission
    permission = UserPermission(
        user_id=user_id,
        permission_type=PermissionType.SMS_READ,
        granted_at=datetime.utcnow(),
        is_active=True
    )
    session.add(permission)
    await session.commit()
    await session.refresh(permission)
    
    logger.info(f"SMS transaction permission granted for user {user_id}")
    
    return {
        "message": "SMS transaction permission granted successfully",
        "permission_id": str(permission.id),
        "granted_at": permission.granted_at.isoformat()
    }


@router.post("/permission/{user_id}/revoke")
async def revoke_sms_transaction_permission(
    user_id: str,
    session: AsyncSession = Depends(get_db_session)
):
    """
    Revoke SMS read permission for a user.
    
    Args:
        user_id: User ID
    
    Returns:
        Permission revocation confirmation
    """
    # Find active permission
    permission = (await session.execute(
        select(UserPermission)
        .filter_by(
            user_id=user_id, 
            permission_type=PermissionType.SMS_READ
        )
        .filter(UserPermission.revoked_at.is_(None))
    )).scalar_one_or_none()
    
    if not permission:
        raise HTTPException(status_code=404, detail="No active SMS transaction permission found")
    
    # Revoke permission
    permission.revoke()
    await session.commit()
    
    logger.info(f"SMS transaction permission revoked for user {user_id}")
    
    return {
        "message": "SMS transaction permission revoked successfully",
        "permission_id": str(permission.id),
        "revoked_at": permission.revoked_at.isoformat()
    }


@router.get("/permission/{user_id}/status")
async def get_sms_transaction_permission_status(
    user_id: str,
    session: AsyncSession = Depends(get_db_session)
):
    """
    Check SMS transaction permission status for a user.
    
    Args:
        user_id: User ID
    
    Returns:
        Permission status
    """
    permission = (await session.execute(
        select(UserPermission)
        .filter_by(
            user_id=user_id, 
            permission_type=PermissionType.SMS_READ
        )
        .order_by(UserPermission.granted_at.desc())
    )).scalar_one_or_none()
    
    if not permission:
        return {
            "has_permission": False,
            "status": "not_granted",
            "message": "SMS transaction permission not yet granted"
        }
    
    if permission.is_granted:
        return {
            "has_permission": True,
            "status": "active",
            "granted_at": permission.granted_at.isoformat(),
            "permission_id": str(permission.id)
        }
    else:
        return {
            "has_permission": False,
            "status": "revoked",
            "granted_at": permission.granted_at.isoformat(),
            "revoked_at": permission.revoked_at.isoformat() if permission.revoked_at else None,
            "permission_id": str(permission.id)
        }


@router.post("/upload/{user_id}")
async def upload_sms_batch(
    user_id: str,
    batch: SmsBatchRequest = Body(...),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Upload a batch of SMS messages from mobile app for processing.
    
    Args:
        user_id: User ID
        batch: Batch of SMS messages
    
    Returns:
        Task information with job ID
    """
    # Validate user exists
    user = (await session.execute(select(User).filter_by(id=user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check SMS permission
    permission = (await session.execute(
        select(UserPermission)
        .filter_by(
            user_id=user_id, 
            permission_type=PermissionType.SMS_READ
        )
        .filter(UserPermission.revoked_at.is_(None))
    )).scalar_one_or_none()
    
    if not permission:
        raise HTTPException(
            status_code=403, 
            detail="SMS transaction permission not granted. Please grant permission first."
        )
    
    if not batch.messages:
        raise HTTPException(status_code=400, detail="No SMS messages provided")
    
    # Convert Pydantic models to dicts for Celery
    messages_data = [
        {
            "sms_id": msg.sms_id,
            "body": msg.body,
            "sender": msg.sender,
            "timestamp": msg.timestamp.isoformat(),
            "thread_id": msg.thread_id
        }
        for msg in batch.messages
    ]
    
    # Queue the task
    task = process_sms_batch_task.delay(user_id, messages_data)
    
    logger.info(f"Started SMS transaction batch processing for user {user_id} ({len(batch.messages)} messages, task_id: {task.id})")
    
    return {
        "message": "SMS transaction batch processing started",
        "task_id": task.id,
        "user_id": user_id,
        "sms_count": len(batch.messages)
    }


@router.get("/status/{user_id}")
async def get_sms_transaction_sync_status(
    user_id: str,
    session: AsyncSession = Depends(get_db_session)
):
    """
    Get SMS transaction sync status for a user.
    
    Args:
        user_id: User ID
    
    Returns:
        Latest job status with progress information
    """
    # Get most recent job
    job = (await session.execute(
        select(SmsTransactionSyncJob)
        .filter_by(user_id=user_id)
        .order_by(SmsTransactionSyncJob.created_at.desc())
    )).scalar_one_or_none()
    
    if not job:
        return {
            "status": "not_started",
            "message": "No SMS transaction sync jobs found for this user"
        }
    
    return {
        "job_id": str(job.id),
        "status": job.status.value,
        "progress": round(job.progress_percentage, 2),
        "total_sms": job.total_sms,
        "processed_sms": job.processed_sms,
        "parsed_transactions": job.parsed_transactions,
        "failed_sms": job.failed_sms,
        "skipped_sms": job.skipped_sms,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "error_log": job.error_log if job.status == JobStatus.FAILED else None
    }


@router.get("/history/{user_id}")
async def get_sms_transaction_sync_history(
    user_id: str,
    limit: int = Query(default=10, ge=1, le=100, description="Number of jobs to return"),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Get SMS transaction sync job history for a user.
    
    Args:
        user_id: User ID
        limit: Maximum number of jobs to return (default: 10, max: 100)
    
    Returns:
        List of past SMS transaction sync jobs
    """
    jobs = (await session.execute(
        select(SmsTransactionSyncJob)
        .filter_by(user_id=user_id)
        .order_by(SmsTransactionSyncJob.created_at.desc())
        .limit(limit)
    )).scalars().all()
    
    return {
        "user_id": user_id,
        "total_jobs": len(jobs),
        "jobs": [
            {
                "job_id": str(job.id),
                "status": job.status.value,
                "progress": round(job.progress_percentage, 2),
                "total_sms": job.total_sms,
                "processed_sms": job.processed_sms,
                "parsed_transactions": job.parsed_transactions,
                "failed_sms": job.failed_sms,
                "skipped_sms": job.skipped_sms,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "created_at": job.created_at.isoformat()
            }
            for job in jobs
        ]
    }
