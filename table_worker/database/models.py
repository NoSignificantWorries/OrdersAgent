from sqlalchemy import Boolean, Column, String

from .base import Base


class Mapping(Base):
    __tablename__ = "mappings"

    source = Column(String, primary_key=True, index=True)
    target = Column(String, nullable=True)
    black_list = Column(Boolean, nullable=False, default=False)
