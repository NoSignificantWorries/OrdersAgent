# models.py
import enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()


class TaskStatus(str, enum.Enum):
    NEW = "new"
    DOWNLOADED = "downloaded"
    FILES_SAVED = "files_saved"
    ML_PROCESSING = "ml_processing"
    ML_CLASSIFIED = "ml_classified"
    ML_LOW_CONFIDENCE = "ml_low_confidence"
    EXCEL_AMBIGUOUS = "excel_ambiguous"
    MANUAL_REVIEW_DONE = "manual_review_done"
    COMPLETED = "completed"
    ERROR = "error"


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    login = Column(String(50), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    pass_hash = Column(String(60), nullable=False)  # bcrypt hash
    role = Column(String(20), nullable=False, default="manager")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Mapping(Base):
    __tablename__ = "mappings"

    source = Column(String(255), primary_key=True)
    target = Column(String(255), nullable=True)
    black_list = Column(Boolean, nullable=False, default=False)


class Email(Base):
    __tablename__ = "emails"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    mailbox = Column(String(100), nullable=False)
    email_uid = Column(BigInteger, nullable=False)
    email_from = Column(Text, nullable=True)
    email_subject = Column(String(500), nullable=True)
    raw_email = Column(Text, nullable=True)
    email_date = Column(DateTime(timezone=True), nullable=True)
    prob_1 = Column(Float, nullable=True)
    predicted_class = Column(SmallInteger, nullable=True)
    model_decision = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    documents = relationship("Document", back_populates="email")
    tasks = relationship("Task", back_populates="email")

    __table_args__ = (UniqueConstraint("mailbox", "email_uid"),)


class Document(Base):
    __tablename__ = "documents"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    email_id = Column(
        BigInteger, ForeignKey("emails.id", ondelete="CASCADE"), nullable=False
    )
    filename = Column(String(500), nullable=True)
    minio_object_key = Column(Text, nullable=True)
    content_type = Column(String(100), nullable=True)
    size_bytes = Column(BigInteger, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    email = relationship("Email", back_populates="documents")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    email_id = Column(
        BigInteger, ForeignKey("emails.id", ondelete="CASCADE"), nullable=False
    )
    document_id = Column(
        BigInteger, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )

    status = Column(
        String(50),
        nullable=False,
        default=TaskStatus.NEW.value,
        index=True,
    )

    # Гибкий результат
    output_data = Column(JSONB, default={})
    # Ручное решение
    manual_decision = Column(JSONB, nullable=True)
    # Кто взял
    assigned_to = Column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)

    email = relationship("Email", back_populates="tasks")
    document = relationship("Document")
    assigned_user = relationship("User")
