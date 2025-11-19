import uuid
from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import UUID
from app.db import Base


class Category(Base):
    __tablename__ = "categories"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    label = Column(String, nullable=False)
    picture = Column(String, nullable=True)

