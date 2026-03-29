"""
Patterns API Routes

Endpoints for recurring pattern analysis and obligation tracking.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from pydantic import BaseModel, Field
import uuid
from datetime import datetime

from app.logging_config import get_logger

logger = get_logger(__name__)

from app.db import get_db_session
from app.dependencies import get_current_user
from app.models import User
from app.models.recurring_pattern import RecurringPattern
from app.models.recurring_pattern_streak import RecurringPatternStreak
from app.services.pattern_service import PatternService


router = APIRouter(prefix="/patterns", tags=["patterns"])


# ===== REQUEST/RESPONSE SCHEMAS =====

class PatternResponse(BaseModel):
    """Pattern response schema"""
    id: str
    transactor: dict
    direction: str
    pattern_type: str
    interval_days: int
    amount_behavior: str
    status: str
    confidence: float
    detected_at: str
    last_evaluated_at: str
    streak: Optional[dict] = None
    obligations: Optional[List[dict]] = None


class ObligationResponse(BaseModel):
    """Obligation response schema"""
    id: str
    recurring_pattern_id: str
    expected_date: str
    tolerance_days: float
    expected_min_amount: Optional[float]
    expected_max_amount: Optional[float]
    status: str
    fulfilled_by_transaction_id: Optional[str]
    fulfilled_at: Optional[str]
    days_early: Optional[float]
    pattern: Optional[dict] = None
    transactor: Optional[dict] = None
    account: Optional[dict] = None


class AnalyzeRequest(BaseModel):
    """Request to trigger pattern analysis"""
    transactor_id: Optional[str] = Field(None, description="Analyze only this transactor")
    direction: Optional[str] = Field(None, description="Filter by type: expense, income, or refund")


class UpdatePatternRequest(BaseModel):
    """Request to manually update pattern"""
    status: Optional[str] = Field(None, description="ACTIVE, PAUSED, or BROKEN")


# ===== ENDPOINTS =====

@router.get("", response_model=List[PatternResponse])
async def get_patterns(
    status: Optional[str] = Query(None, description="Filter by status"),
    include_obligations: bool = Query(True, description="Include upcoming obligations"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Get all recurring patterns for the authenticated user.

    Returns patterns sorted by confidence (highest first).
    """
    logger.debug(f"[API] GET /patterns - user={current_user.id}, status={status}, include_obligations={include_obligations}")

    service = PatternService(db)

    patterns = await service.get_user_patterns(
        user_id=current_user.id,
        status=status,
        include_obligations=include_obligations
    )

    logger.debug(f"[API] Returning {len(patterns)} patterns")

    return patterns


# NOTE: /obligations/upcoming MUST be declared before /{pattern_id} so FastAPI
# does not attempt to treat "obligations" as a pattern_id path parameter.
@router.get("/obligations/upcoming", response_model=List[ObligationResponse])
async def get_upcoming_obligations(
    days_ahead: int = Query(30, ge=1, le=365, description="Look ahead this many days"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Get all upcoming obligations for the authenticated user.

    Returns obligations sorted by expected date (soonest first).
    """
    service = PatternService(db)

    obligations = await service.get_upcoming_obligations(
        user_id=current_user.id,
        days_ahead=days_ahead
    )

    return obligations


@router.get("/{pattern_id}")
async def get_pattern(
    pattern_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Get a specific pattern by ID.
    """
    result = await db.execute(
        select(RecurringPattern)
        .options(
            selectinload(RecurringPattern.transactor),
            selectinload(RecurringPattern.streak),
        )
        .where(
            RecurringPattern.id == uuid.UUID(pattern_id),
            RecurringPattern.user_id == current_user.id
        )
    )
    pattern = result.scalar_one_or_none()

    if not pattern:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pattern not found"
        )

    pattern_dict = pattern.to_dict()

    if pattern.transactor:
        pattern_dict['transactor'] = {
            'id': str(pattern.transactor.id),
            'name': pattern.transactor.name
        }

    if pattern.streak:
        pattern_dict['streak'] = pattern.streak.to_dict()

    service = PatternService(db)
    pattern_dict['obligations'] = await service.get_pattern_obligations(pattern.id)

    return pattern_dict


@router.get("/{pattern_id}/obligations", response_model=List[ObligationResponse])
async def get_pattern_obligations(
    pattern_id: str,
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Get obligations for a specific pattern.
    """
    # Verify pattern belongs to user
    result = await db.execute(
        select(RecurringPattern).where(
            RecurringPattern.id == uuid.UUID(pattern_id),
            RecurringPattern.user_id == current_user.id
        )
    )
    pattern = result.scalar_one_or_none()

    if not pattern:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pattern not found"
        )

    service = PatternService(db)
    obligations = await service.get_pattern_obligations(
        pattern_id=uuid.UUID(pattern_id),
        status=status,
        limit=limit
    )

    return obligations


@router.post("/analyze")
async def analyze_patterns(
    request: AnalyzeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Trigger pattern discovery/analysis for the authenticated user.

    This runs the deterministic pattern discovery algorithm on transaction history.
    Can be filtered to specific transactor or direction.

    Use this:
    - For initial pattern discovery
    - After bulk transaction import
    - For manual pattern refresh
    """
    logger.info(f"[API] POST /patterns/analyze - user={current_user.id}, transactor={request.transactor_id}, direction={request.direction}")

    # Validate direction if provided
    if request.direction and request.direction not in ['expense', 'income', 'refund', 'DEBIT', 'CREDIT']:
        logger.warning(f"[API] Invalid direction value: {request.direction}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid direction. Must be one of: expense, income, refund (or legacy DEBIT, CREDIT)"
        )

    logger.debug(f"[API] Direction filter (if any): {request.direction}")

    service = PatternService(db)

    transactor_id = uuid.UUID(request.transactor_id) if request.transactor_id else None

    discovered = await service.discover_patterns_for_user(
        user_id=current_user.id,
        transactor_id=transactor_id,
        direction=request.direction
    )

    logger.info(f"[API] Pattern discovery complete: {len(discovered)} patterns found")

    return {
        "status": "success",
        "patterns_discovered": len(discovered),
        "patterns": [
            {
                "pattern_id": str(p['pattern'].id),
                "transactor": p['transactor'].name if p.get('transactor') else None,
                "pattern_type": p['pattern'].pattern_type,
                "confidence": float(p['pattern'].confidence),
                "explanation": p['explanation']['explanation_text']
            }
            for p in discovered
        ]
    }


@router.put("/{pattern_id}")
async def update_pattern(
    pattern_id: str,
    request: UpdatePatternRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Manually update a pattern.

    Allows:
    - Pause/resume patterns
    - Mark as broken

    Does NOT allow:
    - Changing interval (unsafe)
    - Changing amount behavior
    """
    result = await db.execute(
        select(RecurringPattern).where(
            RecurringPattern.id == uuid.UUID(pattern_id),
            RecurringPattern.user_id == current_user.id
        )
    )
    pattern = result.scalar_one_or_none()

    if not pattern:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pattern not found"
        )

    # Update allowed fields
    if request.status:
        if request.status not in ['ACTIVE', 'PAUSED', 'BROKEN']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid status. Must be ACTIVE, PAUSED, or BROKEN"
            )
        pattern.status = request.status
        pattern.last_evaluated_at = datetime.utcnow()

    await db.commit()

    return {
        "status": "success",
        "pattern": pattern.to_dict()
    }


@router.delete("/{pattern_id}")
async def delete_pattern(
    pattern_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Delete a pattern.

    This will also delete:
    - Associated streak
    - Pattern-transaction links
    - Pending obligations

    Use with caution.
    """
    result = await db.execute(
        select(RecurringPattern).where(
            RecurringPattern.id == uuid.UUID(pattern_id),
            RecurringPattern.user_id == current_user.id
        )
    )
    pattern = result.scalar_one_or_none()

    if not pattern:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pattern not found"
        )

    await db.delete(pattern)
    await db.commit()

    return {
        "status": "success",
        "message": "Pattern deleted"
    }
