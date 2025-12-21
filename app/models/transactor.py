import uuid
from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db import Base


class Transactor(Base):
    __tablename__ = "transactors"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    name = Column(String, nullable=False)
    user_id = Column(UUID(as_uuid=False), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    source_id = Column(String, nullable=True)
    picture = Column(String, nullable=True)
    label = Column(String, nullable=True)
    
    # Relationship
    user = relationship("User", backref="transactors")

