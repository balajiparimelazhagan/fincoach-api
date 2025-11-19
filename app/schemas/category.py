from typing import Optional
from pydantic import BaseModel


class CategoryBase(BaseModel):
    label: str
    picture: Optional[str] = None


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    label: Optional[str] = None
    picture: Optional[str] = None


class CategoryResponse(CategoryBase):
    id: str

    class Config:
        from_attributes = True

