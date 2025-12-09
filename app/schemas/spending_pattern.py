from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel


# Spending Pattern Schemas

class SpendingPatternBase(BaseModel):
    pattern_type: str  # 'bill' or 'recurring_transaction'
    pattern_name: Optional[str] = None
    frequency_days: Optional[int] = None
    frequency_label: Optional[str] = None
    frequency_variance_days: Optional[int] = None
    average_amount: Optional[Decimal] = None
    min_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None
    amount_variance_percentage: Optional[Decimal] = None
    last_transaction_date: Optional[datetime] = None
    next_expected_date: Optional[datetime] = None
    expected_amount: Optional[Decimal] = None
    occurrence_count: int = 0
    confidence_score: Optional[Decimal] = None
    status: str = 'active'  # 'active', 'paused', 'ended'


class SpendingPatternCreate(SpendingPatternBase):
    transactor_id: Optional[str] = None
    category_id: Optional[str] = None


class SpendingPatternUpdate(BaseModel):
    pattern_name: Optional[str] = None
    frequency_days: Optional[int] = None
    frequency_label: Optional[str] = None
    frequency_variance_days: Optional[int] = None
    average_amount: Optional[Decimal] = None
    expected_amount: Optional[Decimal] = None
    next_expected_date: Optional[datetime] = None
    status: Optional[str] = None
    is_confirmed: Optional[bool] = None


class SpendingPatternResponse(SpendingPatternBase):
    id: str
    user_id: str
    transactor_id: Optional[str] = None
    category_id: Optional[str] = None
    is_confirmed: bool
    detected_by_agent: Optional[str] = None
    detection_method: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    first_transaction_date: Optional[datetime] = None

    class Config:
        from_attributes = True


class SpendingPatternWithTransactions(SpendingPatternResponse):
    """Pattern response with associated transaction IDs"""
    transaction_ids: List[str] = []


class SpendingPatternWithDetails(SpendingPatternResponse):
    """Pattern response with full transactor and category details"""
    transactor_name: Optional[str] = None
    category_label: Optional[str] = None


# Pattern User Feedback Schemas

class PatternUserFeedbackBase(BaseModel):
    feedback_type: str  # 'accepted', 'denied', 'partially_accepted'
    adjusted_frequency_days: Optional[int] = None
    adjusted_amount: Optional[Decimal] = None
    adjusted_variance_percentage: Optional[Decimal] = None
    adjusted_next_date: Optional[datetime] = None
    comment: Optional[str] = None


class PatternUserFeedbackCreate(PatternUserFeedbackBase):
    pattern_id: str


class PatternUserFeedbackUpdate(BaseModel):
    feedback_type: Optional[str] = None
    adjusted_frequency_days: Optional[int] = None
    adjusted_amount: Optional[Decimal] = None
    adjusted_variance_percentage: Optional[Decimal] = None
    adjusted_next_date: Optional[datetime] = None
    comment: Optional[str] = None


class PatternUserFeedbackResponse(PatternUserFeedbackBase):
    id: str
    pattern_id: str
    user_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Pattern Analysis Schemas

class PatternAnalysisRequest(BaseModel):
    """Request to trigger pattern analysis for a user"""
    force_reanalyze: bool = False
    min_occurrences: Optional[int] = None
    min_days_history: Optional[int] = None
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "force_reanalyze": True,
                    "min_occurrences": 3,
                    "min_days_history": 60
                }
            ]
        }
    }


class PatternAnalysisResponse(BaseModel):
    """Response from pattern analysis"""
    status: str  # 'processing', 'completed', 'skipped'
    total_patterns: Optional[int] = None
    bill_patterns_count: Optional[int] = None
    recurring_patterns_count: Optional[int] = None
    duplicates_removed: Optional[int] = None
    reason: Optional[str] = None
    existing_pattern_count: Optional[int] = None
    task_id: Optional[str] = None  # Celery task ID for async processing


# Bulk Pattern Response

class UserPatternsResponse(BaseModel):
    """All patterns for a user"""
    total_count: int
    bill_patterns: List[SpendingPatternWithDetails]
    recurring_patterns: List[SpendingPatternWithDetails]
    active_count: int
    paused_count: int
    ended_count: int
