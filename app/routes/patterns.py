"""
Spending Pattern Routes

API endpoints for managing spending patterns and user feedback.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_

from app.db import get_sync_db_session
from app.models.spending_pattern import SpendingPattern
from app.models.pattern_user_feedback import PatternUserFeedback
from app.models.transactor import Transactor
from app.models.category import Category
from app.schemas.spending_pattern import (
    SpendingPatternResponse,
    SpendingPatternWithDetails,
    SpendingPatternUpdate,
    PatternUserFeedbackCreate,
    PatternUserFeedbackResponse,
    PatternUserFeedbackUpdate,
    PatternAnalysisRequest,
    PatternAnalysisResponse,
    UserPatternsResponse
)
from agent.pattern_analyzer_coordinator import PatternAnalyzerCoordinator
from app.logging_config import get_logger
from app.config import settings

logger = get_logger(__name__)

router = APIRouter(prefix="/patterns", tags=["Spending Patterns"])


def _enrich_pattern_with_details(pattern: SpendingPattern) -> dict:
    """Add transactor and category details to pattern"""
    pattern_dict = {
        "id": pattern.id,
        "user_id": pattern.user_id,
        "transactor_id": pattern.transactor_id,
        "category_id": pattern.category_id,
        "pattern_type": pattern.pattern_type,
        "pattern_name": pattern.pattern_name,
        "frequency_days": pattern.frequency_days,
        "frequency_label": pattern.frequency_label,
        "frequency_variance_days": pattern.frequency_variance_days,
        "average_amount": float(pattern.average_amount) if pattern.average_amount else None,
        "min_amount": float(pattern.min_amount) if pattern.min_amount else None,
        "max_amount": float(pattern.max_amount) if pattern.max_amount else None,
        "amount_variance_percentage": float(pattern.amount_variance_percentage) if pattern.amount_variance_percentage else None,
        "last_transaction_date": pattern.last_transaction_date,
        "next_expected_date": pattern.next_expected_date,
        "expected_amount": float(pattern.expected_amount) if pattern.expected_amount else None,
        "occurrence_count": pattern.occurrence_count,
        "confidence_score": float(pattern.confidence_score) if pattern.confidence_score else None,
        "status": pattern.status,
        "is_confirmed": pattern.is_confirmed,
        "detected_by_agent": pattern.detected_by_agent,
        "detection_method": pattern.detection_method,
        "created_at": pattern.created_at,
        "updated_at": pattern.updated_at,
        "first_transaction_date": pattern.first_transaction_date,
        "transactor_name": pattern.transactor.name if pattern.transactor else None,
        "category_label": pattern.category.label if pattern.category else None,
    }
    return pattern_dict


@router.post("/analyze/{user_id}", response_model=PatternAnalysisResponse)
def analyze_user_patterns(
    user_id: str,
    request: PatternAnalysisRequest,
    db: Session = Depends(get_sync_db_session)
):
    """
    Trigger pattern analysis for a user (async via Celery with job tracking).
    Detects both bill patterns and recurring transaction patterns.
    Creates a job record and returns job_id for status tracking.
    """
    logger.info(f"Pattern analysis requested for user {user_id}")
    
    try:
        from app.celery.celery_tasks import analyze_spending_patterns
        from app.models.pattern_analysis_job import PatternAnalysisJob, JobStatus
        from datetime import datetime, timezone
        import uuid
        
        # Get configuration - use request params if provided, otherwise use config defaults
        min_occurrences = request.min_occurrences if request.min_occurrences is not None else getattr(settings, 'PATTERN_MIN_OCCURRENCES', 3)
        min_days_history = request.min_days_history if request.min_days_history is not None else getattr(settings, 'PATTERN_MIN_DAYS_HISTORY', 60)
        
        logger.info(
            f"Pattern analysis config: min_occurrences={min_occurrences}, "
            f"min_days_history={min_days_history} "
            f"(from {'request' if request.min_occurrences is not None or request.min_days_history is not None else 'config'})"
        )
        
        # Create job record (use timezone-naive datetime for DB compatibility)
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        job = PatternAnalysisJob(
            id=uuid.uuid4(),
            user_id=user_id,
            status=JobStatus.PENDING,
            force_reanalyze=str(request.force_reanalyze),
            min_occurrences=min_occurrences,
            min_days_history=min_days_history,
            created_at=now_utc,
            updated_at=now_utc
        )
        
        db.add(job)
        db.commit()
        db.refresh(job)
        
        # Trigger async Celery task with job_id
        task = analyze_spending_patterns.apply_async(
            args=[user_id, request.force_reanalyze, str(job.id)],
            queue='scheduling'
        )
        
        logger.info(f"Pattern analysis job {job.id} created and task {task.id} queued for user {user_id}")
        
        return PatternAnalysisResponse(
            status="pending",
            total_patterns=None,
            bill_patterns_count=None,
            recurring_patterns_count=None,
            duplicates_removed=None,
            reason=f"Pattern analysis job created (job_id: {job.id})",
            existing_pattern_count=None,
            task_id=str(job.id)
        )
    
    except Exception as e:
        logger.error(f"Error creating pattern analysis job for user {user_id}: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create pattern analysis job: {str(e)}")


@router.get("/job/{job_id}")
def get_job_status(job_id: str, db: Session = Depends(get_sync_db_session)):
    """
    Check the status of a pattern analysis job.
    Returns job details including progress, patterns found, and any errors.
    """
    try:
        from app.models.pattern_analysis_job import PatternAnalysisJob
        
        job = db.query(PatternAnalysisJob).filter(PatternAnalysisJob.id == job_id).first()
        
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        
        return {
            "job_id": str(job.id),
            "user_id": str(job.user_id),
            "status": job.status.value,
            "progress_percentage": job.progress_percentage,
            "current_step": job.current_step,
            "total_transactors": job.total_transactors,
            "processed_transactors": job.processed_transactors,
            "bill_patterns_found": job.bill_patterns_found,
            "recurring_patterns_found": job.recurring_patterns_found,
            "total_patterns_found": job.total_patterns_found,
            "duplicates_removed": job.duplicates_removed,
            "force_reanalyze": job.force_reanalyze,
            "error_message": job.error_message,
            "error_log": job.error_log,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching job {job_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch job status: {str(e)}")


@router.get("/user/{user_id}", response_model=UserPatternsResponse)
def get_user_patterns(
    user_id: str,
    status: Optional[str] = Query(None, description="Filter by status: active, paused, ended"),
    pattern_type: Optional[str] = Query(None, description="Filter by type: bill, recurring_transaction"),
    db: Session = Depends(get_sync_db_session)
):
    """
    Get all spending patterns for a user.
    """
    query = db.query(SpendingPattern).options(
        joinedload(SpendingPattern.transactor),
        joinedload(SpendingPattern.category)
    ).filter(SpendingPattern.user_id == user_id)
    
    # Apply filters
    if status:
        query = query.filter(SpendingPattern.status == status)
    if pattern_type:
        query = query.filter(SpendingPattern.pattern_type == pattern_type)
    
    patterns = query.all()
    
    # Separate by type and enrich with details
    bill_patterns = []
    recurring_patterns = []
    
    for pattern in patterns:
        enriched = _enrich_pattern_with_details(pattern)
        if pattern.pattern_type == 'bill':
            bill_patterns.append(enriched)
        else:
            recurring_patterns.append(enriched)
    
    # Count by status
    active_count = sum(1 for p in patterns if p.status == 'active')
    paused_count = sum(1 for p in patterns if p.status == 'paused')
    ended_count = sum(1 for p in patterns if p.status == 'ended')
    
    return UserPatternsResponse(
        total_count=len(patterns),
        bill_patterns=bill_patterns,
        recurring_patterns=recurring_patterns,
        active_count=active_count,
        paused_count=paused_count,
        ended_count=ended_count
    )


@router.get("/{pattern_id}", response_model=SpendingPatternWithDetails)
def get_pattern(
    pattern_id: str,
    db: Session = Depends(get_sync_db_session)
):
    """
    Get a specific spending pattern by ID.
    """
    pattern = db.query(SpendingPattern).options(
        joinedload(SpendingPattern.transactor),
        joinedload(SpendingPattern.category)
    ).filter(SpendingPattern.id == pattern_id).first()
    
    if not pattern:
        raise HTTPException(status_code=404, detail="Pattern not found")
    
    return _enrich_pattern_with_details(pattern)


@router.patch("/{pattern_id}", response_model=SpendingPatternResponse)
def update_pattern(
    pattern_id: str,
    update_data: SpendingPatternUpdate,
    db: Session = Depends(get_sync_db_session)
):
    """
    Update a spending pattern.
    Allows users to adjust pattern details.
    """
    pattern = db.query(SpendingPattern).filter(
        SpendingPattern.id == pattern_id
    ).first()
    
    if not pattern:
        raise HTTPException(status_code=404, detail="Pattern not found")
    
    # Update fields
    update_dict = update_data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(pattern, field, value)
    
    db.commit()
    db.refresh(pattern)
    
    logger.info(f"Pattern {pattern_id} updated")
    
    return pattern


@router.delete("/{pattern_id}")
def delete_pattern(
    pattern_id: str,
    db: Session = Depends(get_sync_db_session)
):
    """
    Delete a spending pattern.
    """
    pattern = db.query(SpendingPattern).filter(
        SpendingPattern.id == pattern_id
    ).first()
    
    if not pattern:
        raise HTTPException(status_code=404, detail="Pattern not found")
    
    db.delete(pattern)
    db.commit()
    
    logger.info(f"Pattern {pattern_id} deleted")
    
    return {"message": "Pattern deleted successfully"}


# Pattern User Feedback Endpoints

@router.post("/{pattern_id}/feedback", response_model=PatternUserFeedbackResponse)
def submit_pattern_feedback(
    pattern_id: str,
    feedback: PatternUserFeedbackCreate,
    db: Session = Depends(get_sync_db_session)
):
    """
    Submit user feedback for a pattern.
    Allows users to accept, deny, or partially accept patterns.
    """
    # Verify pattern exists
    pattern = db.query(SpendingPattern).filter(
        SpendingPattern.id == pattern_id
    ).first()
    
    if not pattern:
        raise HTTPException(status_code=404, detail="Pattern not found")
    
    # Create feedback
    feedback_obj = PatternUserFeedback(
        pattern_id=pattern_id,
        user_id=pattern.user_id,
        feedback_type=feedback.feedback_type,
        adjusted_frequency_days=feedback.adjusted_frequency_days,
        adjusted_amount=feedback.adjusted_amount,
        adjusted_variance_percentage=feedback.adjusted_variance_percentage,
        adjusted_next_date=feedback.adjusted_next_date,
        comment=feedback.comment
    )
    
    db.add(feedback_obj)
    
    # Update pattern based on feedback
    if feedback.feedback_type == 'accepted':
        pattern.is_confirmed = True
        # Increase confidence score
        if pattern.confidence_score:
            pattern.confidence_score = min(float(pattern.confidence_score) + 10, 100)
    
    elif feedback.feedback_type == 'denied':
        pattern.status = 'ended'
        pattern.is_confirmed = False
    
    elif feedback.feedback_type == 'partially_accepted':
        pattern.is_confirmed = True
        # Apply user adjustments
        if feedback.adjusted_frequency_days:
            pattern.frequency_days = feedback.adjusted_frequency_days
        if feedback.adjusted_amount:
            pattern.expected_amount = feedback.adjusted_amount
        if feedback.adjusted_variance_percentage:
            pattern.amount_variance_percentage = feedback.adjusted_variance_percentage
        if feedback.adjusted_next_date:
            pattern.next_expected_date = feedback.adjusted_next_date
    
    db.commit()
    db.refresh(feedback_obj)
    
    logger.info(
        f"Feedback submitted for pattern {pattern_id}: {feedback.feedback_type}"
    )
    
    return feedback_obj


@router.get("/{pattern_id}/feedback", response_model=List[PatternUserFeedbackResponse])
def get_pattern_feedback(
    pattern_id: str,
    db: Session = Depends(get_sync_db_session)
):
    """
    Get all feedback for a specific pattern.
    """
    feedbacks = db.query(PatternUserFeedback).filter(
        PatternUserFeedback.pattern_id == pattern_id
    ).order_by(PatternUserFeedback.created_at.desc()).all()
    
    return feedbacks


@router.post("/{pattern_id}/reanalyze")
def reanalyze_pattern(
    pattern_id: str,
    db: Session = Depends(get_sync_db_session)
):
    """
    Trigger reanalysis of a specific pattern.
    """
    pattern = db.query(SpendingPattern).filter(
        SpendingPattern.id == pattern_id
    ).first()
    
    if not pattern:
        raise HTTPException(status_code=404, detail="Pattern not found")
    
    try:
        min_occurrences = getattr(settings, 'PATTERN_MIN_OCCURRENCES', 3)
        min_days_history = getattr(settings, 'PATTERN_MIN_DAYS_HISTORY', 60)
        
        coordinator = PatternAnalyzerCoordinator(
            db=db,
            min_occurrences=min_occurrences,
            min_days_history=min_days_history
        )
        
        updated_pattern = coordinator.reanalyze_pattern(pattern_id)
        
        if not updated_pattern:
            raise HTTPException(status_code=404, detail="Pattern not found after reanalysis")
        
        return {
            "message": "Pattern reanalyzed successfully",
            "pattern_id": pattern_id,
            "updated_at": updated_pattern.updated_at
        }
    
    except Exception as e:
        logger.error(f"Error reanalyzing pattern {pattern_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Reanalysis failed: {str(e)}")
