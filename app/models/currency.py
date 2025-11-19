import uuid
from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import UUID
from app.db import Base


class Currency(Base):
    __tablename__ = "currencies"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    name = Column(String, nullable=False)
    value = Column(String, nullable=False)  # Currency code (e.g., USD, EUR)
    country = Column(String, nullable=False)

