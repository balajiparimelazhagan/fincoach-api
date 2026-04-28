from fastapi import APIRouter, Depends
from app.dependencies import get_current_user
from app.models.user import User
from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/spending-analysis", tags=["Spending Analysis"])


@router.post("/trigger")
async def trigger_spending_analysis(
    current_user: User = Depends(get_current_user),
):
    """Queue pattern discovery for the current user as a background Celery task."""
    from app.celery.celery_tasks import analyze_spending_patterns
    task = analyze_spending_patterns.delay(str(current_user.id))

    logger.info(f"Queued spending analysis for user {current_user.id} (task_id: {task.id})")

    return {
        "message": "Spending analysis queued",
        "task_id": task.id,
        "user_id": str(current_user.id),
    }


@router.get("/status")
async def get_spending_analysis_status():
    """Return current spending analysis configuration."""
    return {
        "in_days": settings.SPENDING_ANALYSIS_IN_DAYS,
    }
