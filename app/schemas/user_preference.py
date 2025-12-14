from typing import Dict, Any
from datetime import datetime
from pydantic import BaseModel


class UserPreferenceResponse(BaseModel):
    id: str
    user_id: str
    ui_preferences: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserPreferenceUpdate(BaseModel):
    ui_preferences: Dict[str, Any]
