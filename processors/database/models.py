from datetime import datetime
from enum import Enum
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

# ============================================================
# ENUM-ы (совпадают с PG enum-ами)
# ============================================================


class TaskType(str, Enum):
    CLASSIFY_EMAIL = "classify_email"
    MANUAL_CLASSIFY = "manual_classify"
    PARSE_DOCUMENTS = "parse_documents"
    MANUAL_IDENTIFY_MATERIALS = "manual_identify_materials"
    REPARSE_WITH_MANUAL_INPUT = "reparse_with_manual_input"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# ============================================================
# Модели
# ============================================================


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    login: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    pass_hash: Mapped[str] = mapped_column(String(60), nullable=False)  # bcrypt hash
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="manager")
    current_load: Mapped[int] = mapped_column(Integer, default=0)

    mail_access_token: Mapped[Optional[str]] = mapped_column(Text)
    mail_refresh_token: Mapped[Optional[str]] = mapped_column(Text)
    mail_access_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()")
    )


class Email(Base):
    __tablename__ = "emails"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    target_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    email_uid: Mapped[Optional[int]] = mapped_column(BigInteger, unique=True)
    email_from: Mapped[Optional[str]] = mapped_column(Text)
    email_subject: Mapped[Optional[str]] = mapped_column(String(255))
    email_body: Mapped[Optional[str]] = mapped_column(Text)
    email_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()")
    )

    target_user: Mapped[Optional["User"]] = relationship("User")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("emails.id", ondelete="CASCADE"), nullable=False
    )
    document_name: Mapped[Optional[str]] = mapped_column(String(255))
    object_bucket: Mapped[Optional[str]] = mapped_column(Text)
    object_key: Mapped[Optional[str]] = mapped_column(Text)
    document_data: Mapped[Optional[bytes]] = mapped_column(Text)  # BYTEA
    result_document_name: Mapped[Optional[str]] = mapped_column(String(255))
    result_document_data: Mapped[Optional[bytes]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()")
    )

    email: Mapped["Email"] = relationship("Email")


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index(
            "idx_tasks_next",
            "priority",
            "created_at",
            postgresql_where=text("status = 'pending'"),
        ),
        Index(
            "idx_tasks_type_pending",
            "type",
            "priority",
            "created_at",
            postgresql_where=text("status = 'pending'"),
        ),
        Index("idx_tasks_email", "email_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("emails.id", ondelete="CASCADE"), nullable=False
    )

    type: Mapped[TaskType] = mapped_column(
        SAEnum(TaskType, name="task_type", create_type=False), nullable=False
    )
    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus, name="task_status", create_type=False),
        nullable=False,
        default=TaskStatus.PENDING,
    )

    priority: Mapped[int] = mapped_column(Integer, default=100)
    assigned_to: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )

    input_data: Mapped[Any] = mapped_column(JSON, default=dict)
    output_data: Mapped[Any] = mapped_column(JSON, default=dict)

    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()")
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    email: Mapped["Email"] = relationship("Email")
    assigned_user: Mapped[Optional["User"]] = relationship("User")


class Mapping(Base):
    __tablename__ = "mappings"

    source = Column(String, primary_key=True, index=True)
    target = Column(String, nullable=True)
    black_list = Column(Boolean, nullable=False, default=False)
