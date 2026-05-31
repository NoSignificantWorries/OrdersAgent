from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from database import (
    EmailsQueueRepository,
    EmailsRepository,
    EmailTaskStatus,
    EmailType,
    FilesQueueRepository,
    FilesRepository,
    FileTaskStatus,
    ModelDecision,
    UnitOfWork,
    get_db_session,
)
from database.base import Base


class NewTaskItem(BaseModel):
    subject: str = Field(...)
    body: str = Field(...)
    files: List[str] = Field([])
    date: datetime = Field(...)
    model_config = ConfigDict(from_attributes=True)


class EmailItem(BaseModel):
    id: int = Field(...)
    archived: bool = Field(...)
    type: EmailType = Field(...)
    subject: str = Field(...)
    body: str = Field(...)
    with_files: bool = Field(...)
    date: datetime = Field(...)
    created_at: datetime = Field(...)
    archived_at: Optional[datetime] = Field(...)
    model_config = ConfigDict(from_attributes=True)


class EmailTaskItem(BaseModel):
    id: int = Field(...)
    email_id: int = Field(...)
    prob: Optional[float] = Field(...)
    model_decision: ModelDecision = Field(...)
    status: EmailTaskStatus = Field(...)
    input: str = Field(...)
    output: str = Field(...)
    errors: str = Field(...)
    warnings: str = Field(...)
    created_at: datetime = Field(...)
    model_config = ConfigDict(from_attributes=True)


class FileItem(BaseModel):
    id: int = Field(...)
    email_id: int = Field(...)
    origin_minio_key: str = Field(...)
    result_minio_key: Optional[str] = Field(...)
    created_at: datetime = Field(...)
    completed_at: Optional[datetime] = Field(...)
    model_config = ConfigDict(from_attributes=True)


class FileTaskItem(BaseModel):
    id: int = Field(...)
    email_task_id: int = Field(...)
    file_id: int = Field(...)
    status: FileTaskStatus = Field(...)
    errors: str = Field(...)
    warnings: str = Field(...)
    created_at: datetime = Field(...)
    model_config = ConfigDict(from_attributes=True)


class ClassificationResults(BaseModel):
    type: EmailType = Field(...)
    prob: Optional[float] = Field(None)
    model_decision: ModelDecision = Field(ModelDecision.CLASSIFIED)


class NewTaskResponse(BaseModel):
    ok: bool
    files_count: int
    email_task: EmailTaskItem
    files: List[FileItem]
    files_tasks: List[FileTaskItem]


class TaskCloseResponse(BaseModel):
    ok: bool
    email: EmailItem


class TaskClassifiedResponse(BaseModel):
    ok: bool
    email_task: EmailTaskItem
    file_tasks_count: int


router = APIRouter(prefix="/task", tags=["tasks", "emails", "files"])


@router.post("/add-new-email-task", response_model=NewTaskResponse)
async def add_new_task(
    body: NewTaskItem, session: AsyncSession = Depends(get_db_session)
):
    async with UnitOfWork(session) as uow:
        emails_repo = EmailsRepository(uow.session)
        files_repo = FilesRepository(uow.session)
        emails_queue_repo = EmailsQueueRepository(uow.session)
        files_queue_repo = FilesQueueRepository(uow.session)

        email_obj = await emails_repo.add_user(
            subject=body.subject,
            body=body.body,
            date=body.date,
            with_files=bool(body.files),
        )
        email_task = await emails_queue_repo.add_task(email_id=email_obj.id)
        if body.files:
            files = await files_repo.add_many(email_id=email_obj.id, files=body.files)
            files_tasks = await files_queue_repo.add_many(
                email_task_id=email_task.id, files_indexes=[file.id for file in files]
            )
        else:
            files = []
            files_tasks = []

    return NewTaskResponse(
        ok=True,
        files_count=len(files),
        email_task=email_task,
        files=files,
        files_tasks=files_tasks,
    )


@router.post("/mark-email-task-classified", response_model=TaskClassifiedResponse)
async def task_classified(
    body: ClassificationResults,
    id: int = Query("Email's task id"),
    session: AsyncSession = Depends(get_db_session),
):
    async with UnitOfWork(session) as uow:
        emails_repo = EmailsRepository(uow.session)
        files_repo = FilesRepository(uow.session)
        emails_queue_repo = EmailsQueueRepository(uow.session)
        files_queue_repo = FilesQueueRepository(uow.session)

        email_task = await emails_queue_repo.update(
            id=id,
            model_decision=body.model_decision,
            prob=body.prob,
            status=EmailTaskStatus.CLASSIFIED,
        )
        email = await emails_repo.update(id=email_task.email_id, type=body.type)
        files_tasks_count = await files_queue_repo.update_by_email_task_id(
            email_task_id=email_task.email_id, status=FileTaskStatus.PROCESSING
        )

    return TaskClassifiedResponse(
        ok=True,
        email_task=email_task,
        file_tasks_count=files_tasks_count,
    )


@router.post("/close-by-email-id", response_model=TaskCloseResponse)
async def close_task(
    id: int = Query(..., description="Email's id"),
    session: AsyncSession = Depends(get_db_session),
):
    async with UnitOfWork(session) as uow:
        emails_repo = EmailsRepository(uow.session)
        emails_queue_repo = EmailsQueueRepository(uow.session)

        email = await emails_repo.get_by_id(id=id)
        email_task = await emails_queue_repo.get_by_email_id(email_id=id)
        await emails_queue_repo.delete(id=email_task.id)
        email = await emails_repo.mark_archived(id=email.id)

    return TaskCloseResponse(ok=True, email=email)
