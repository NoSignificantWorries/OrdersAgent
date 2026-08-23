from io import BytesIO
from urllib.parse import quote
from zipfile import ZipFile, ZIP_DEFLATED
import re
from math import ceil

from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.db import get_db_pool
from app.routers import auth
from app.services.sent import list_sent_for_user, get_sent_email_detail_for_user
from app.cloud.minio import MinIOClient


router = APIRouter(prefix="/api", tags=["sent"])
SENT_ATTACHMENTS_BUCKET = "outgoing-attachments"


async def _load_sent_document_bytes_from_storage(bucket_name: str, object_key: str) -> bytes:
    client = MinIOClient.get_client()
    response = client.get_object(bucket_name, object_key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def _build_safe_zip_name(subject: str | None, email_id: int) -> str:
    base = (subject or "").strip()

    if not base:
        return f"sent-email-{email_id}-attachments.zip"

    base = re.sub(r'[\\/*?:"<>|]+', " ", base)
    base = re.sub(r"\s+", " ", base).strip()
    base = base.rstrip(". ")

    if not base:
        return f"sent-email-{email_id}-attachments.zip"

    if len(base) > 120:
        base = base[:120].rstrip()

    return f"{base}.zip"


@router.get("/sent")
async def get_sent(
    request: Request,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=100, ge=1, le=100),
    search: str = "",
    sort: str = Query(default="newest"),
):
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    result = await list_sent_for_user(
        user=user,
        page=page,
        per_page=per_page,
        search=search,
        sort=sort,
    )

    total = int(result.get("total", 0))
    items = list(result.get("items", []))
    total_pages = max(1, ceil(total / per_page)) if total > 0 else 1

    return {
        "user": {
            "id": user["id"],
            "email": user["email"],
            "role": user.get("role"),
        },
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "count": len(items),
        "items": items,
    }


@router.get("/sent/{email_id}/detail")
async def get_sent_detail(email_id: int, request: Request):
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    item = await get_sent_email_detail_for_user(
        user=user,
        email_id=email_id,
    )

    if not item:
        raise HTTPException(status_code=404, detail="Исходящее письмо не найдено")

    return {
        "ok": True,
        "item": item,
    }


@router.get("/sent/{email_id}/attachments/download-all")
async def download_all_sent_documents(email_id: int, request: Request):
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    pool = await get_db_pool()

    async with pool.acquire() as conn:
        if user.get("role") == "admin":
            email_row = await conn.fetchrow(
                """
                SELECT
                    se.id,
                    se.mailbox,
                    se.email_subject
                FROM sent_emails se
                WHERE se.id = $1
                """,
                email_id,
            )
        else:
            email_row = await conn.fetchrow(
                """
                SELECT
                    se.id,
                    se.mailbox,
                    se.email_subject
                FROM sent_emails se
                WHERE se.id = $1
                  AND se.mailbox = $2
                """,
                email_id,
                user["email"],
            )

        if not email_row:
            raise HTTPException(status_code=404, detail="Исходящее письмо не найдено")

        docs = await conn.fetch(
            """
            SELECT
                sd.id,
                sd.filename,
                sd.minio_object_key
            FROM sent_documents sd
            WHERE sd.sent_email_id = $1
            ORDER BY sd.id
            """,
            email_id,
        )

    files_to_zip: list[tuple[str, str]] = []

    for doc in docs:
        object_key = doc["minio_object_key"]
        filename = doc["filename"] or f"sent-document-{doc['id']}"

        if not object_key:
            continue

        print(f"SENT DOWNLOAD TRY: bucket={SENT_ATTACHMENTS_BUCKET}, object_key={object_key}")

        files_to_zip.append((object_key, filename))

    if not files_to_zip:
        raise HTTPException(status_code=404, detail="Вложения отсутствуют")

    if len(files_to_zip) == 1:
        object_key, filename = files_to_zip[0]

        try:
            print(f"SENT DOWNLOAD SINGLE TRY: bucket={SENT_ATTACHMENTS_BUCKET}, object_key={object_key}")
            file_bytes = await _load_sent_document_bytes_from_storage(
                SENT_ATTACHMENTS_BUCKET,
                object_key,
            )
        except Exception as e:
            print(f"SENT DOWNLOAD SINGLE ERROR: email_id={email_id}, object_key={object_key}, error={e}")
            error_text = str(e)
            if "NoSuchKey" in error_text or "NoSuchObject" in error_text:
                raise HTTPException(status_code=404, detail="Файл не найден")
            raise HTTPException(status_code=500, detail=f"Ошибка чтения файла: {e}")

        return StreamingResponse(
            BytesIO(file_bytes),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
            },
        )

    zip_buffer = BytesIO()

    with ZipFile(zip_buffer, mode="w", compression=ZIP_DEFLATED) as zip_file:
        for object_key, archive_name in files_to_zip:
            try:
                print(f"SENT DOWNLOAD SINGLE TRY: bucket={SENT_ATTACHMENTS_BUCKET}, object_key={object_key}")
                file_bytes = await _load_sent_document_bytes_from_storage(
                    SENT_ATTACHMENTS_BUCKET,
                    object_key,
                )
            except Exception as e:
                print(f"SENT DOWNLOAD ZIP ERROR: email_id={email_id}, object_key={object_key}, error={e}")
                error_text = str(e)
                if "NoSuchKey" in error_text or "NoSuchObject" in error_text:
                    continue
                raise HTTPException(status_code=500, detail=f"Ошибка чтения файла: {e}")

            zip_file.writestr(archive_name, file_bytes)

    zip_buffer.seek(0)

    zip_name = _build_safe_zip_name(email_row["email_subject"], email_id)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(zip_name)}"
        },
    )