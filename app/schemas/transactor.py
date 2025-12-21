from typing import Optional
from pydantic import BaseModel


class TransactorBase(BaseModel):
    name: str
    source_id: Optional[str] = None
    picture: Optional[str] = None
    label: Optional[str] = None


class TransactorCreate(TransactorBase):
    pass


class TransactorUpdate(BaseModel):
    name: Optional[str] = None
    source_id: Optional[str] = None
    picture: Optional[str] = None
    label: Optional[str] = None


class TransactorResponse(TransactorBase):
    id: str
    user_id: str

    class Config:
        from_attributes = True

