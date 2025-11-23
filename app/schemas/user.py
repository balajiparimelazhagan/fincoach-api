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
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_expiry: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    name: Optional[str] = None
    picture: Optional[str] = None
    google_credentials_json: Optional[str] = None
    google_token_pickle: Optional[str] = None
    currency_id: Optional[str] = None

