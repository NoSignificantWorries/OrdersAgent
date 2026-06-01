from enum import Enum as PyEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from .base import Base


class UserStatus(str, PyEnum):
    STANDART = "standart"
    MANAGER = "manager"
    ADMIN = "admin"


class ModelDecision(str, PyEnum):
    REVIEW = "review"
    CLASSIFIED = "classified"
    NOT_CLASSIFIED = "not-classified"


class EmailType(str, PyEnum):
    UNKNOWN = "unknown"
    REQUEST = "request"
    CALLCULATION = "callculation"
    QUESTION = "question"


class EmailTaskStatus(str, PyEnum):
    NEW = "new"
    CLASSIFIED = "classified"
    MANUAL_REVIEW_WAITING = "manual-review"
    MANUALLY_REVIEWED = "manually-reviewed"
    ERROR = "error"
    COMPLETED = "completed"


class FileTaskStatus(str, PyEnum):
    NEW = "new"
    PROCESSING = "processing"
    ERROR = "error"
    COMPLETED = "completed"


class Users(Base):
    __tablename__ = "users"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    status = Column(
        Enum(UserStatus, name="user_status_enum"),
        default=UserStatus.STANDART,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("email", name="uq_user_email"),
        Index("idx_user_status", "status"),
        {"comment": "System users"},
    )


class Emails(Base):
    __tablename__ = "emails"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    archived = Column(Boolean, default=False, nullable=False)
    type = Column(
        Enum(EmailType, name="email_type_enum"),
        default=EmailType.UNKNOWN,
        nullable=False,
    )
    subject = Column(Text, default="", nullable=False)
    body = Column(Text, default="", nullable=False)
    with_files = Column(Boolean, default=False, nullable=False)
    date = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    archived_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_email_type", "type"),
        {"comment": "Emails storage"},
    )


class Files(Base):
    __tablename__ = "files"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    email_id = Column(
        BigInteger,
        ForeignKey("emails.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    origin_minio_key = Column(Text, nullable=False)
    result_minio_key = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = ({"comment": "Emails storage"},)


class EmailsQueue(Base):
    __tablename__ = "emails_queue"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    email_id = Column(
        BigInteger,
        ForeignKey("emails.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    prob = Column(Float, nullable=True)
    model_decision = Column(
        Enum(ModelDecision, name="model_decision_enum"),
        default=ModelDecision.NOT_CLASSIFIED,
        nullable=False,
    )
    status = Column(
        Enum(EmailTaskStatus, name="email_task_status_enum"),
        default=EmailTaskStatus.NEW,
        nullable=False,
    )
    input = Column(JSONB, default="{}", nullable=False)
    output = Column(JSONB, default="{}", nullable=False)
    errors = Column(JSONB, default="{}", nullable=False)
    warnings = Column(JSONB, default="{}", nullable=False)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


EmailsQueue.__tableargs__ = (
    Index(
        "idx_email_tasks_new",
        "status",
        "created_at",
        postgresql_where=(EmailsQueue.status == EmailTaskStatus.NEW),
    ),
    {"comment": "Emails tasks queue"},
)


class FilesQueue(Base):
    __tablename__ = "files_queue"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    email_task_id = Column(
        BigInteger,
        ForeignKey("emails_queue.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_id = Column(
        BigInteger,
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = Column(
        Enum(FileTaskStatus, name="file_task_status_enum"),
        default=FileTaskStatus.NEW,
        nullable=False,
    )
    errors = Column(JSONB, default="{}", nullable=False)
    warnings = Column(JSONB, default="{}", nullable=False)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = ({"comment": "Files tasks queue"},)


class Materials(Base):
    __tablename__ = "materials"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source = Column(String(255), nullable=False, unique=True, index=True)
    target = Column(String(255), nullable=True)
    article = Column(String(255), nullable=True)
    black_list = Column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    __table_args__ = (
        Index("idx_materials_source", "source"),
        Index("idx_materials_black_list", "black_list"),
        {"comment": "Materials and articles"},
    )
