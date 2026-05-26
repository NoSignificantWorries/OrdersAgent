import json
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

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

class MaterialsManualDecisionUpdate(BaseModel):
    manual_decision: dict[str, list]


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
        if not object_key:
            continue

        try:
            client.stat_object(RESULTS_BUCKET, object_key)
            result_docs.append({
                "id": doc["id"],
                "filename": doc["filename"] or f"document-{doc['id']}",
            })

        # Предпочтительно ловить конкретный тип ошибки MinIO SDK.
        # Например:
        # except S3Error as e:
        #     if e.code in ("NoSuchKey", "NoSuchObject"):
        #         continue
        #     raise HTTPException(status_code=500, detail=f"Ошибка проверки файла: {e}")

        except Exception as e:
            error_text = str(e)
            if "NoSuchKey" in error_text or "NoSuchObject" in error_text:
                continue
            raise HTTPException(status_code=500, detail=f"Ошибка проверки файла: {e}")

    return {"documents": result_docs}


@router.get("/queue")
async def get_queue(
    request: Request,
    status: str = "",
    limit: int | None = None,
):
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if limit is not None:
        if limit < 1:
            limit = 1
        if limit > 200:
            limit = 200

    items = await list_queue_for_user(user=user, status=status, limit=limit)

    return {
        "user": {
            "id": user["id"],
            "email": user["email"],
            "role": user.get("role"),
        },
        "count": len(items),
        "items": items,
    }

async def _download_document_by_id(
    document_id: int,
    request: Request,
    bucket_name: str,
    not_found_detail: str = "Файл не найден",
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

    object_key = row["minio_object_key"]
    filename = row["filename"] or f"document-{document_id}"

    if not object_key:
        raise HTTPException(status_code=404, detail="У файла отсутствует object_key")

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


@router.get("/documents/{document_id}/result-download")
async def download_result_document(document_id: int, request: Request):
    return await _download_document_by_id(
        document_id=document_id,
        request=request,
        bucket_name=RESULTS_BUCKET,
        not_found_detail="Файл не найден",
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

                if not isinstance(value, list) or len(value) != 2:
                    raise HTTPException(
                        status_code=400,
                        detail=f"manual_decision['{material}'] должен быть массивом [answer, blacklist]"
                    )

                user_value = str(value[0] or "").strip()
                blacklist_value = bool(value[1])

                if not user_value:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Для материала '{material}' не заполнено значение"
                    )

                normalized_manual_decision[material] = [user_value, blacklist_value]

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

@router.delete("/emails/{email_id}")
async def delete_email(email_id: int, request: Request):
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    pool = await get_db_pool()
    file_keys: list[str] = []

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT e.id, e.mailbox, t.id AS task_id, t.status
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

            allowed_statuses = {"question", "error", "completed"}
            current_status = row["status"]

            if current_status not in allowed_statuses:
                raise HTTPException(
                    status_code=400,
                    detail=f"Удаление доступно только для статусов question, error, completed. Текущий статус: {current_status}"
                )

            docs = await conn.fetch(
                """
                SELECT minio_object_key
                FROM documents
                WHERE email_id = $1
                  AND minio_object_key IS NOT NULL
                """,
                email_id,
            )

            file_keys = [doc["minio_object_key"] for doc in docs if doc["minio_object_key"]]

            await conn.execute(
                """
                DELETE FROM emails
                WHERE id = $1
                """,
                email_id,
            )

    client = MinIOClient.get_client()
    storage_errors = []

    for object_key in file_keys:
        for bucket_name in (SOURCE_ATTACHMENTS_BUCKET, RESULTS_BUCKET):
            try:
                client.remove_object(bucket_name, object_key)
            except Exception as e:
                error_text = str(e)
                if "NoSuchKey" in error_text or "NoSuchObject" in error_text:
                    continue
                storage_errors.append({
                    "bucket": bucket_name,
                    "object_key": object_key,
                    "error": error_text,
                })

    if storage_errors:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Письмо удалено из БД, но часть файлов не удалена из MinIO",
                "storage_errors": storage_errors,
            },
        )

    return {"ok": True, "email_id": email_id}