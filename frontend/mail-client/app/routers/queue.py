import json
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from urllib.parse import quote
import httpx

from typing import Annotated
from fastapi import APIRouter, Request, HTTPException, Form, File, UploadFile
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, Field, ConfigDict
from pathlib import Path

from app.db import get_db_pool
from app.routers import auth
from app.services.queue import list_queue_for_user
from app.cloud.minio import MinIOClient


router = APIRouter(prefix="/api", tags=["queue"])
SOURCE_ATTACHMENTS_BUCKET = "orders-attachments"
RESULTS_BUCKET = "results"

class DecisionUpdate(BaseModel):
    predicted_class: int | None = None
    model_decision: str | None = None
    status: str | None = None

class MaterialManualDecisionItem(BaseModel):
    target: str | None = None
    article: str | None = None
    black_list: bool = Field(default=False, alias="black-list")

    model_config = ConfigDict(populate_by_name=True)

class MaterialsManualDecisionUpdate(BaseModel):
    manual_decision: dict[str, MaterialManualDecisionItem]

class EmailReadUpdate(BaseModel):
    is_read: bool

async def _load_document_bytes_from_storage(bucket_name: str, object_key: str) -> bytes:
    client = MinIOClient.get_client()
    response = client.get_object(bucket_name, object_key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()

@router.get("/tasks/{task_id}/result-documents")
async def get_result_documents(task_id: int, request: Request):
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    pool = await get_db_pool()

    async with pool.acquire() as conn:
        if user.get("role") == "admin":
            task = await conn.fetchrow(
                """
                SELECT
                    t.id,
                    t.email_id,
                    e.mailbox
                FROM tasks t
                JOIN emails e ON e.id = t.email_id
                WHERE t.id = $1
                """,
                task_id,
            )
        else:
            task = await conn.fetchrow(
                """
                SELECT
                    t.id,
                    t.email_id,
                    e.mailbox
                FROM tasks t
                JOIN emails e ON e.id = t.email_id
                WHERE t.id = $1
                  AND e.mailbox = $2
                """,
                task_id,
                user["email"],
            )

        if not task:
            raise HTTPException(status_code=404, detail="Задача не найдена")

        docs = await conn.fetch(
            """
            SELECT
                d.id,
                d.filename,
                d.minio_object_key
            FROM documents d
            WHERE d.email_id = $1
            ORDER BY d.id
            """,
            task["email_id"],
        )

    client = MinIOClient.get_client()
    result_docs = []

    for doc in docs:
        object_key = doc["minio_object_key"]
        filename = doc["filename"] or f"document-{doc['id']}"

        if not object_key:
            continue

        candidates = [
            {
                "variant": "main",
                "object_key": object_key,
                "filename": filename,
            }
        ]

        display_filename2 = Path(filename).stem + "_(articles)" + Path(filename).suffix
        object_key_filename2 = Path(object_key).stem + "_(articles)" + Path(object_key).suffix
        object_key2 = str(Path(object_key).with_name(object_key_filename2))

        candidates.append(
            {
                "variant": "articles",
                "object_key": object_key2,
                "filename": display_filename2,
            }
        )

        for candidate in candidates:
            try:
                client.stat_object(RESULTS_BUCKET, candidate["object_key"])
                result_docs.append({
                    "id": doc["id"],
                    "filename": candidate["filename"],
                    "variant": candidate["variant"],
                })
            except Exception as e:
                error_text = str(e)
                if "NoSuchKey" in error_text or "NoSuchObject" in error_text:
                    continue
                raise HTTPException(status_code=500, detail=f"Ошибка проверки файла: {e}")

    return {"documents": result_docs}

@router.get("/tasks/{task_id}/result-documents/download-all")
async def download_all_result_documents(task_id: int, request: Request):
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    pool = await get_db_pool()

    async with pool.acquire() as conn:
        if user.get("role") == "admin":
            task = await conn.fetchrow(
                """
                SELECT
                    t.id,
                    t.email_id,
                    e.mailbox
                FROM tasks t
                JOIN emails e ON e.id = t.email_id
                WHERE t.id = $1
                """,
                task_id,
            )
        else:
            task = await conn.fetchrow(
                """
                SELECT
                    t.id,
                    t.email_id,
                    e.mailbox
                FROM tasks t
                JOIN emails e ON e.id = t.email_id
                WHERE t.id = $1
                  AND e.mailbox = $2
                """,
                task_id,
                user["email"],
            )

        if not task:
            raise HTTPException(status_code=404, detail="Задача не найдена")

        docs = await conn.fetch(
            """
            SELECT
                d.id,
                d.filename,
                d.minio_object_key
            FROM documents d
            WHERE d.email_id = $1
            ORDER BY d.id
            """,
            task["email_id"],
        )

    files_to_zip: list[tuple[str, str]] = []

    for doc in docs:
        base_object_key = doc["minio_object_key"]
        base_filename = doc["filename"] or f"document-{doc['id']}"

        if not base_object_key:
            continue

        files_to_zip.append((base_object_key, base_filename))

        articles_display_filename = (
            Path(base_filename).stem + "_(articles)" + Path(base_filename).suffix
        )
        articles_object_key_filename = (
            Path(base_object_key).stem + "_(articles)" + Path(base_object_key).suffix
        )
        articles_object_key = str(
            Path(base_object_key).with_name(articles_object_key_filename)
        )

        client = MinIOClient.get_client()
        try:
            client.stat_object(RESULTS_BUCKET, articles_object_key)
            files_to_zip.append((articles_object_key, articles_display_filename))
        except Exception as e:
            error_text = str(e)
            if "NoSuchKey" in error_text or "NoSuchObject" in error_text:
                pass
            else:
                raise HTTPException(status_code=500, detail=f"Ошибка проверки файла: {e}")

    if not files_to_zip:
        raise HTTPException(status_code=404, detail="Результирующие файлы отсутствуют")

    zip_buffer = BytesIO()
    with ZipFile(zip_buffer, mode="w", compression=ZIP_DEFLATED) as zip_file:
        for object_key, archive_name in files_to_zip:
            try:
                file_bytes = await _load_document_bytes_from_storage(RESULTS_BUCKET, object_key)
            except Exception as e:
                error_text = str(e)
                if "NoSuchKey" in error_text or "NoSuchObject" in error_text:
                    continue
                raise HTTPException(status_code=500, detail=f"Ошибка чтения файла: {e}")

            zip_file.writestr(archive_name, file_bytes)

    zip_buffer.seek(0)

    zip_name = f"task-{task_id}-results.zip"
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(zip_name)}"
        },
    )

@router.get("/queue")
async def get_queue(
    request: Request,
    status: str = "",
    limit: int = 100,           # фиксированный размер страницы
    offset: int = 0,            # смещение
    archived: bool | None = None,
):
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Защита от некорректных значений
    if limit < 1:
        limit = 100
    if limit > 500:             # максимум 500 (можно оставить 100, но пусть будет запас)
        limit = 500

    items, total = await list_queue_for_user(
        user=user,
        status=status,
        limit=limit,
        offset=offset,
        archived=archived,
    )

    return {
        "user": {
            "id": user["id"],
            "email": user["email"],
            "role": user.get("role"),
        },
        "items": items,
        "total": total,          # общее количество записей (для пагинации)
        "offset": offset,
        "limit": limit,
        "count": len(items),     # оставляем для обратной совместимости (опционально)
    }

async def _download_document_by_id(
    document_id: int,
    request: Request,
    bucket_name: str,
    not_found_detail: str = "Файл не найден",
    variant: str = "main",
):
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    pool = await get_db_pool()

    async with pool.acquire() as conn:
        if user.get("role") == "admin":
            row = await conn.fetchrow(
                """
                SELECT
                    d.id,
                    d.filename,
                    d.minio_object_key,
                    d.email_id,
                    e.mailbox
                FROM documents d
                JOIN emails e ON e.id = d.email_id
                WHERE d.id = $1
                """,
                document_id,
            )
        else:
            row = await conn.fetchrow(
                """
                SELECT
                    d.id,
                    d.filename,
                    d.minio_object_key,
                    d.email_id,
                    e.mailbox
                FROM documents d
                JOIN emails e ON e.id = d.email_id
                WHERE d.id = $1
                  AND e.mailbox = $2
                """,
                document_id,
                user["email"],
            )

    if not row:
        raise HTTPException(status_code=404, detail=not_found_detail)

    base_object_key = row["minio_object_key"]
    base_filename = row["filename"] or f"document-{document_id}"

    if not base_object_key:
        raise HTTPException(status_code=404, detail="У файла отсутствует object_key")

    if variant == "main":
        object_key = base_object_key
        filename = base_filename
    elif variant == "articles":
        display_filename = Path(base_filename).stem + "_(articles)" + Path(base_filename).suffix
        object_key_filename = Path(base_object_key).stem + "_(articles)" + Path(base_object_key).suffix

        filename = display_filename
        object_key = str(Path(base_object_key).with_name(object_key_filename))
    else:
        raise HTTPException(status_code=400, detail="Некорректный variant")

    try:
        file_bytes = await _load_document_bytes_from_storage(bucket_name, object_key)
    except Exception as e:
        error_text = str(e)
        if "NoSuchKey" in error_text or "NoSuchObject" in error_text:
            raise HTTPException(status_code=404, detail=not_found_detail)
        raise HTTPException(status_code=500, detail=f"Ошибка чтения файла: {e}")

    return StreamingResponse(
        BytesIO(file_bytes),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
        },
    )


@router.get("/documents/{document_id}/download")
async def download_source_document(document_id: int, request: Request):
    return await _download_document_by_id(
        document_id=document_id,
        request=request,
        bucket_name=SOURCE_ATTACHMENTS_BUCKET,
        not_found_detail="Файл не найден",
    )

@router.get("/emails/{email_id}/attachments/download-all")
async def download_all_source_documents(email_id: int, request: Request):
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    pool = await get_db_pool()

    async with pool.acquire() as conn:
        if user.get("role") == "admin":
            email_row = await conn.fetchrow(
                """
                SELECT
                    e.id,
                    e.mailbox
                FROM emails e
                WHERE e.id = $1
                """,
                email_id,
            )
        else:
            email_row = await conn.fetchrow(
                """
                SELECT
                    e.id,
                    e.mailbox
                FROM emails e
                WHERE e.id = $1
                  AND e.mailbox = $2
                """,
                email_id,
                user["email"],
            )

        if not email_row:
            raise HTTPException(status_code=404, detail="Письмо не найдено")

        docs = await conn.fetch(
            """
            SELECT
                d.id,
                d.filename,
                d.minio_object_key
            FROM documents d
            WHERE d.email_id = $1
            ORDER BY d.id
            """,
            email_id,
        )

    files_to_zip: list[tuple[str, str]] = []

    for doc in docs:
        object_key = doc["minio_object_key"]
        filename = doc["filename"] or f"document-{doc['id']}"

        if not object_key:
            continue

        files_to_zip.append((object_key, filename))

    if not files_to_zip:
        raise HTTPException(status_code=404, detail="Вложения отсутствуют")

    zip_buffer = BytesIO()
    with ZipFile(zip_buffer, mode="w", compression=ZIP_DEFLATED) as zip_file:
        for object_key, archive_name in files_to_zip:
            try:
                file_bytes = await _load_document_bytes_from_storage(
                    SOURCE_ATTACHMENTS_BUCKET,
                    object_key,
                )
            except Exception as e:
                error_text = str(e)
                if "NoSuchKey" in error_text or "NoSuchObject" in error_text:
                    continue
                raise HTTPException(status_code=500, detail=f"Ошибка чтения файла: {e}")

            zip_file.writestr(archive_name, file_bytes)

    zip_buffer.seek(0)

    zip_name = f"email-{email_id}-attachments.zip"
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(zip_name)}"
        },
    )

@router.get("/documents/{document_id}/result-download")
async def download_result_document(
    document_id: int,
    request: Request,
    variant: str = "main",
):
    return await _download_document_by_id(
        document_id=document_id,
        request=request,
        bucket_name=RESULTS_BUCKET,
        not_found_detail="Файл не найден",
        variant=variant,
    )

@router.post("/queue/{task_id}/decision")
async def update_queue_decision(
    task_id: int,
    payload: DecisionUpdate,
    request: Request,
):
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if payload.predicted_class is None and payload.model_decision is None:
        raise HTTPException(status_code=400, detail="Нечего обновлять")

    pool = await get_db_pool()

    async with pool.acquire() as conn:
        async with conn.transaction():
            if user.get("role") == "admin":
                task_row = await conn.fetchrow(
                    """
                    SELECT
                        t.id,
                        t.email_id,
                        t.status,
                        t.assigned_to,
                        t.output_data,
                        e.mailbox,
                        e.email_uid
                    FROM tasks t
                    JOIN emails e ON e.id = t.email_id
                    WHERE t.id = $1
                    """,
                    task_id,
                )
            else:
                task_row = await conn.fetchrow(
                    """
                    SELECT
                        t.id,
                        t.email_id,
                        t.status,
                        t.assigned_to,
                        t.output_data,
                        e.mailbox,
                        e.email_uid
                    FROM tasks t
                    JOIN emails e ON e.id = t.email_id
                    WHERE t.id = $1
                      AND e.mailbox = $2
                    """,
                    task_id,
                    user["email"],
                )

            if not task_row:
                raise HTTPException(status_code=404, detail="Задача не найдена")


            model_decision = payload.model_decision
            predicted_class = payload.predicted_class

            if payload.status is not None:
                next_status = payload.status
            elif model_decision == "question":
                next_status = "question"
            else:
                next_status = "ml_classified"

            if predicted_class is None:
                if model_decision == "request":
                    predicted_class = 2
                elif model_decision == "question":
                    predicted_class = 1
                elif model_decision == "calculation":
                    predicted_class = 0
                elif model_decision == "review":
                    predicted_class = None

            if model_decision not in {"request", "calculation", "question"}:
                raise HTTPException(
                    status_code=400,
                    detail="Нужно выбрать итоговый класс: 'Заявка', 'Расчёт' или 'Вопрос'"
                )

            if predicted_class not in {0, 1, 2}:
                raise HTTPException(
                    status_code=400,
                    detail="Итоговый класс должен быть 0, 1 или 2"
                )

            output_patch = {
                "predicted_class": predicted_class,
                "manual_updated_by": user["id"],
                "manual_review": True,
            }

            if model_decision is not None:
                output_patch["model_decision"] = model_decision

            updated_task = await conn.fetchrow(
                """
                UPDATE tasks
                SET
                    output_data = COALESCE(output_data, '{}'::jsonb) || $1::jsonb,
                    status = $2::task_status,
                    assigned_to = $3,
                    completed_at = NOW()
                WHERE id = $4
                RETURNING
                    id,
                    email_id,
                    status,
                    assigned_to,
                    output_data,
                    completed_at
                """,
                json.dumps(output_patch),
                next_status,
                user["id"],
                task_id,
            )

            await conn.execute(
                """
                UPDATE emails
                SET
                    predicted_class = $1,
                    model_decision = $2
                WHERE id = $3
                """,
                predicted_class,
                model_decision,
                task_row["email_id"],
            )

    return {
        "ok": True,
        "task": {
            "id": updated_task["id"],
            "email_id": updated_task["email_id"],
            "status": updated_task["status"],
            "assigned_to": updated_task["assigned_to"],
            "output_data": updated_task["output_data"] or {},
            "completed_at": updated_task["completed_at"].isoformat() if updated_task["completed_at"] else None,
        },
        "email": {
            "id": task_row["email_id"],
            "email_uid": task_row["email_uid"],
        },
    }

@router.post("/queue/{task_id}/manual-decision")
async def update_materials_manual_decision(
    task_id: int,
    payload: MaterialsManualDecisionUpdate,
    request: Request,
):
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not payload.manual_decision:
        raise HTTPException(status_code=400, detail="manual_decision пустой")

    pool = await get_db_pool()

    async with pool.acquire() as conn:
        async with conn.transaction():
            if user.get("role") == "admin":
                task_row = await conn.fetchrow(
                    """
                    SELECT
                        t.id,
                        t.email_id,
                        t.status,
                        t.assigned_to,
                        t.output_data,
                        e.mailbox,
                        e.email_uid
                    FROM tasks t
                    JOIN emails e ON e.id = t.email_id
                    WHERE t.id = $1
                    """,
                    task_id,
                )
            else:
                task_row = await conn.fetchrow(
                    """
                    SELECT
                        t.id,
                        t.email_id,
                        t.status,
                        t.assigned_to,
                        t.output_data,
                        e.mailbox,
                        e.email_uid
                    FROM tasks t
                    JOIN emails e ON e.id = t.email_id
                    WHERE t.id = $1
                      AND e.mailbox = $2
                    """,
                    task_id,
                    user["email"],
                )

            if not task_row:
                raise HTTPException(status_code=404, detail="Задача не найдена")

            current_status = task_row["status"]
            if current_status != "materials_review":
                raise HTTPException(
                    status_code=400,
                    detail=f"manual_decision можно сохранить только для статуса materials_review, сейчас: {current_status}",
                )

            normalized_manual_decision = {}

            for material, value in payload.manual_decision.items():
                if not isinstance(material, str) or not material.strip():
                    raise HTTPException(status_code=400, detail="Некорректный ключ материала")

                target_value = (value.target or "").strip() or None
                article_value = (value.article or "").strip() or None
                blacklist_value = bool(value.black_list)

                normalized_manual_decision[material] = {
                    "target": target_value,
                    "article": article_value,
                    "black-list": blacklist_value,
                }

            updated_task = await conn.fetchrow(
                """
                UPDATE tasks
                SET
                    manual_decision = $1::jsonb,
                    status = 'manual_review_done'::task_status,
                    assigned_to = $2,
                    completed_at = NOW()
                WHERE id = $3
                RETURNING
                    id,
                    email_id,
                    status,
                    assigned_to,
                    manual_decision,
                    output_data,
                    completed_at
                """,
                json.dumps(normalized_manual_decision, ensure_ascii=False),
                user["id"],
                task_id,
            )

    return {
        "ok": True,
        "task": {
            "id": updated_task["id"],
            "email_id": updated_task["email_id"],
            "status": updated_task["status"],
            "assigned_to": updated_task["assigned_to"],
            "manual_decision": updated_task["manual_decision"] or {},
            "output_data": updated_task["output_data"] or {},
            "completed_at": updated_task["completed_at"].isoformat() if updated_task["completed_at"] else None,
        },
        "email": {
            "id": task_row["email_id"],
            "email_uid": task_row["email_uid"],
        },
    }

@router.post("/emails/{email_id}/archive")
async def archive_email(email_id: int, request: Request):
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    pool = await get_db_pool()

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT e.id, e.archived, t.id AS task_id, t.status
                FROM emails e
                LEFT JOIN tasks t ON t.email_id = e.id
                WHERE e.id = $1
                ORDER BY t.created_at DESC NULLS LAST
                LIMIT 1
                """,
                email_id,
            )

            if not row:
                raise HTTPException(status_code=404, detail="Письмо не найдено")

            if row["status"] is None:
                raise HTTPException(status_code=400, detail="У письма нет связанной задачи")

            # allowed_statuses = {"question", "error", "completed"}
            # current_status = row["status"]

            # if current_status not in allowed_statuses:
            #     raise HTTPException(
            #         status_code=400,
            #         detail=(
            #             "Архивация доступна только для статусов "
            #             "question, error, completed. "
            #             f"Текущий статус: {current_status}"
            #         ),
            #     )

            if row["archived"]:
                return {"ok": True, "email_id": email_id, "archived": True}

            await conn.execute(
                """
                UPDATE emails
                SET archived = TRUE
                WHERE id = $1
                """,
                email_id,
            )

    return {"ok": True, "email_id": email_id, "archived": True}


@router.post("/emails/{email_id}/unarchive")
async def unarchive_email(email_id: int, request: Request):
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    pool = await get_db_pool()

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT id, archived
                FROM emails
                WHERE id = $1
                LIMIT 1
                """,
                email_id,
            )

            if not row:
                raise HTTPException(status_code=404, detail="Письмо не найдено")

            if not row["archived"]:
                return {"ok": True, "email_id": email_id, "archived": False}

            await conn.execute(
                """
                UPDATE emails
                SET archived = FALSE
                WHERE id = $1
                """,
                email_id,
            )

    return {"ok": True, "email_id": email_id, "archived": False}

@router.patch("/emails/{email_id}/read")
async def update_email_read_status(
    email_id: int,
    payload: EmailReadUpdate,
    request: Request,
):
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    pool = await get_db_pool()

    async with pool.acquire() as conn:
        async with conn.transaction():
            if user.get("role") == "admin":
                row = await conn.fetchrow(
                    """
                    SELECT id, mailbox, is_read
                    FROM emails
                    WHERE id = $1
                    LIMIT 1
                    """,
                    email_id,
                )
            else:
                row = await conn.fetchrow(
                    """
                    SELECT id, mailbox, is_read
                    FROM emails
                    WHERE id = $1
                      AND mailbox = $2
                    LIMIT 1
                    """,
                    email_id,
                    user["email"],
                )

            if not row:
                raise HTTPException(status_code=404, detail="Письмо не найдено")

            if row["is_read"] == payload.is_read:
                return {
                    "ok": True,
                    "email_id": email_id,
                    "is_read": payload.is_read,
                }

            await conn.execute(
                """
                UPDATE emails
                SET is_read = $1
                WHERE id = $2
                """,
                payload.is_read,
                email_id,
            )

    return {
        "ok": True,
        "email_id": email_id,
        "is_read": payload.is_read,
    }


@router.post("/emails/{email_id}/reply", status_code=204)
async def reply_to_email(
    email_id: int,
    request: Request,
    body: Annotated[str, Form(...)],
    attachments: Annotated[list[UploadFile] | None, File()] = None,
):
    attachments = attachments or []
    
    print("reply_to_email called")
    print("email_id =", email_id)
    print("body =", body)
    print("attachments count =", len(attachments))
    print("attachment names =", [a.filename for a in attachments])

    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not body.strip():
        raise HTTPException(status_code=400, detail="body is empty")

    pool = await get_db_pool()

    async with pool.acquire() as conn:
        if user.get("role") == "admin":
            row = await conn.fetchrow(
                """
                SELECT id, mailbox
                FROM emails
                WHERE id = $1
                LIMIT 1
                """,
                email_id,
            )
        else:
            row = await conn.fetchrow(
                """
                SELECT id, mailbox
                FROM emails
                WHERE id = $1
                  AND mailbox = $2
                LIMIT 1
                """,
                email_id,
                user["email"],
            )

    if not row:
        raise HTTPException(status_code=404, detail="Письмо не найдено")

    mail_service_url = f"http://mail:8080/emails/{email_id}/reply"

    files = []
    try:
        for attachment in attachments:
            content = await attachment.read()
            files.append(
                (
                    "attachments",
                    (
                        attachment.filename or "attachment",
                        content,
                        attachment.content_type or "application/octet-stream",
                    ),
                )
            )

        print("forwarding to mail service")
        print("files payload =", [(name, meta[0], meta[2]) for name, meta in files])

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                mail_service_url,
                data={"body": body},
                files=files,
            )
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Mail service unavailable: {e}") from e

    if resp.status_code != 204:
        print("mail service status =", resp.status_code)
        print("mail service text =", resp.text)

        detail = "Не удалось отправить ответное письмо"
        
        # Сначала пробуем получить JSON
        try:
            data = resp.json()
            # Если есть detail в JSON, используем его
            if data.get("detail"):
                detail = data["detail"]
            # Если ответ содержит текст ошибки напрямую
            elif resp.text and resp.text.strip():
                detail = resp.text.strip()
        except Exception:
            # Если не JSON, берем текст ответа
            if resp.text and resp.text.strip():
                detail = resp.text.strip()

        raise HTTPException(status_code=resp.status_code, detail=detail)

    return Response(status_code=204)

@router.post("/emails/send", status_code=204)
async def send_email(
    request: Request,
    to: Annotated[str, Form(...)],
    body: Annotated[str, Form(...)],
    subject: Annotated[str, Form()] = "",
    attachments: Annotated[list[UploadFile] | None, File()] = None,
):
    attachments = attachments or []

    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    to = (to or "").strip()
    subject = (subject or "").strip()
    body = body or ""

    if not to:
        raise HTTPException(status_code=400, detail="to is empty")

    if not body.strip():
        raise HTTPException(status_code=400, detail="body is empty")

    files = []
    try:
        for attachment in attachments:
            content = await attachment.read()
            files.append(
                (
                    "attachments",
                    (
                        attachment.filename or "attachment",
                        content,
                        attachment.content_type or "application/octet-stream",
                    ),
                )
            )

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "http://mail:8080/emails/send",
                data={
                    "mailbox": user["email"],
                    "to": to,
                    "subject": subject,
                    "body": body,
                },
                files=files,
            )

    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Mail service unavailable: {e}") from e

    if resp.status_code != 204:
        detail = "Не удалось отправить письмо"
        
        try:
            data = resp.json()
            # Если есть detail в JSON, используем его
            if data.get("detail"):
                detail = data["detail"]
            # Если ответ содержит текст ошибки напрямую
            elif resp.text and resp.text.strip():
                detail = resp.text.strip()
        except Exception:
            # Если не JSON, берем текст ответа
            if resp.text and resp.text.strip():
                detail = resp.text.strip()

        raise HTTPException(status_code=resp.status_code, detail=detail)

    return Response(status_code=204)