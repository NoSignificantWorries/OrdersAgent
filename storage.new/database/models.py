import uuid
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean,
    Column,
    Enum,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from .base import Base


class UserStatus(str, PyEnum):
    STANDART = "standart"
    MANAGER = "manager"
    ADMIN = "admin"


class EmailTaskStatus(str, PyEnum):
    NEW = "new"
    CLASSIFIED = "classified"
    MANUAL_REVIEW_WAITING = "manual-review"
    MANUALLY_REVIEWED = "manually-reviewed"
    ERROR = "error"
    COMPLETED = "completed"


class FileTaskStatus(str, PyEnum):
    NEW = "new"
    ERROR = "error"
    COMPLETED = "completed"


class Users(Base):
    __tablename__ = "users"
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    email = Column(String(255), nullable=False, unique=True, index=True)
    status = Column(
        Enum(UserStatus, name="user_status_enum"),
        default=UserStatus.STANDART,
        nullable=False,
        # server_default=text("'standart'::user_status_enum"),
    )

    __table_args__ = (
        UniqueConstraint("email", name="uq_user_email"),
        Index("idx_user_status", "status"),
        {"comment": "System users"},
    )


class Materials(Base):
    __tablename__ = "materials"
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    source = Column(String(255), nullable=False, unique=True, index=True)
    target = Column(String(255), nullable=True)
    black_list = Column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    __table_args__ = (
        Index("idx_materials_source", "source"),
        Index("idx_materials_black_list", "black_list"),
        {"comment": "Materials and articles"},
    )
