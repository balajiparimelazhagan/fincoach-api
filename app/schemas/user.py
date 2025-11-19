from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class UserResponse(BaseModel):
    id: str
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None
    currency_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    name: Optional[str] = None
    picture: Optional[str] = None
    currency_id: Optional[str] = None

