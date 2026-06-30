from __future__ import annotations

from typing import Any
import json
from email import policy
from email.parser import BytesParser

from app.db import get_db_pool


def _normalize_documents(raw_documents):
    if not raw_documents:
        return []

    parsed = raw_documents

    if isinstance(raw_documents, str):
        try:
            parsed = json.loads(raw_documents)
        except json.JSONDecodeError:
            return []

    if isinstance(parsed, dict):
        parsed = [parsed]

    if not isinstance(parsed, list):
        return []

    result = []
    for doc in parsed:
        if not isinstance(doc, dict):
            continue

        result.append({
            "id": doc.get("id"),
            "filename": doc.get("filename") or doc.get("document_name") or "",
            "document_name": doc.get("document_name") or doc.get("filename") or "",
            "content_type": doc.get("content_type") or "",
            "size_bytes": doc.get("size_bytes"),
            "created_at": doc.get("created_at"),
            "object_key": doc.get("object_key") or doc.get("minio_object_key") or "",
            "minio_object_key": doc.get("minio_object_key") or doc.get("object_key") or "",
            "object_bucket": doc.get("object_bucket"),
            "has_document_data": doc.get("has_document_data"),
            "result_document_name": doc.get("result_document_name"),
            "has_result_document_data": doc.get("has_result_document_data"),
        })

    return result


def _extract_body_text_from_raw_email(raw_email: str | None) -> str:
    if not raw_email:
        return ""

    try:
        message = BytesParser(policy=policy.default).parsebytes(raw_email.encode("utf-8", errors="ignore"))
    except Exception:
        return raw_email.strip()

    plain_parts: list[str] = []

    if message.is_multipart():
        for part in message.walk():
            content_disposition = (part.get_content_disposition() or "").lower()
            content_type = (part.get_content_type() or "").lower()

            if content_disposition == "attachment":
                continue

            if content_type == "text/plain":
                try:
                    text = part.get_content()
                except Exception:
                    try:
                        payload = part.get_payload(decode=True)
                        charset = part.get_content_charset() or "utf-8"
                        text = payload.decode(charset, errors="ignore") if payload else ""
                    except Exception:
                        text = ""

                if text and text.strip():
                    plain_parts.append(text.strip())
    else:
        content_type = (message.get_content_type() or "").lower()
        if content_type == "text/plain":
            try:
                return (message.get_content() or "").strip()
            except Exception:
                try:
                    payload = message.get_payload(decode=True)
                    charset = message.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="ignore").strip() if payload else ""
                except Exception:
                    return raw_email.strip()

    if plain_parts:
        return "\n\n".join(plain_parts).strip()

    return ""


async def list_sent_for_user(
    user: dict,
    page: int = 1,
    per_page: int = 100,
    search: str = "",
    sort: str = "newest",
) -> dict:
    pool = await get_db_pool()

    if page < 1:
        page = 1

    if per_page < 1:
        per_page = 1
    if per_page > 100:
        per_page = 100

    offset = (page - 1) * per_page
    is_admin = user.get("role") == "admin"

    where_clauses: list[str] = []
    params: list[object] = []
    param_idx = 1

    if not is_admin:
        where_clauses.append(f"se.mailbox = ${param_idx}")
        params.append(user["email"])
        param_idx += 1

    normalized_search = (search or "").strip()
    if normalized_search:
        where_clauses.append(
            f"""(
                COALESCE(se.email_subject, '') ILIKE ${param_idx}
                OR COALESCE(se.to_header, '') ILIKE ${param_idx}
                OR COALESCE(se.email_from, '') ILIKE ${param_idx}
                OR COALESCE(se.raw_email, '') ILIKE ${param_idx}
            )"""
        )
        params.append(f"%{normalized_search}%")
        param_idx += 1

    where_sql = ""
    if where_clauses:
        where_sql = "\nWHERE " + "\n  AND ".join(where_clauses)

    sort_sql = "ASC" if sort == "oldest" else "DESC"

    count_sql = f"""
        SELECT COUNT(*) AS total
        FROM sent_emails se
        {where_sql}
    """

    page_sql = f"""
        SELECT
            se.id AS sent_email_id,
            se.user_id,
            se.mailbox,
            se.email_uid,
            se.message_id,
            se.in_reply_to,
            se.references_header AS references,
            se.parent_email_id,
            se.email_from,
            se.reply_to,
            se.to_header,
            se.cc_header,
            se.bcc_header,
            se.email_subject,
            se.raw_email,
            se.email_date,
            se.send_status,
            se.created_at,
            se.sent_at,

            COALESCE(
                jsonb_agg(
                    DISTINCT jsonb_build_object(
                        'id', sd.id,
                        'document_name', sd.filename,
                        'filename', sd.filename,
                        'object_bucket', NULL,
                        'object_key', sd.minio_object_key,
                        'minio_object_key', sd.minio_object_key,
                        'content_type', sd.content_type,
                        'size_bytes', sd.size_bytes,
                        'has_document_data',
                            CASE
                                WHEN sd.size_bytes IS NOT NULL AND sd.size_bytes > 0 THEN true
                                ELSE false
                            END,
                        'result_document_name', NULL,
                        'has_result_document_data', false,
                        'created_at', sd.created_at
                    )
                ) FILTER (WHERE sd.id IS NOT NULL),
                '[]'::jsonb
            ) AS documents

        FROM sent_emails se
        LEFT JOIN sent_documents sd
            ON sd.sent_email_id = se.id
        {where_sql}
        GROUP BY
            se.id,
            se.user_id,
            se.mailbox,
            se.email_uid,
            se.message_id,
            se.in_reply_to,
            se.references_header,
            se.parent_email_id,
            se.email_from,
            se.reply_to,
            se.to_header,
            se.cc_header,
            se.bcc_header,
            se.email_subject,
            se.raw_email,
            se.email_date,
            se.send_status,
            se.created_at,
            se.sent_at
        ORDER BY
            COALESCE(se.sent_at, se.email_date, se.created_at) {sort_sql},
            se.id {sort_sql}
        LIMIT ${param_idx}
        OFFSET ${param_idx + 1}
    """

    async with pool.acquire() as conn:
        total_row = await conn.fetchrow(count_sql, *params)
        total = int(total_row["total"] or 0)

        page_params = [*params, per_page, offset]
        rows = await conn.fetch(page_sql, *page_params)

    result: list[dict] = []

    for row in rows:
        documents = _normalize_documents(row["documents"])
        body_text = _extract_body_text_from_raw_email(row["raw_email"])

        item: dict = {
            "id": row["sent_email_id"],
            "emailid": row["sent_email_id"],
            "messageid": row["message_id"],
            "inreplyto": row["in_reply_to"],
            "references": row["references"],
            "parentemailid": row["parent_email_id"],
            "userid": row["user_id"],
            "mailbox": row["mailbox"],
            "emailuid": row["email_uid"],
            "emailfrom": row["email_from"],
            "replyto": row["reply_to"],
            "toheader": row["to_header"],
            "ccheader": row["cc_header"],
            "bccheader": row["bcc_header"],
            "emailsubject": row["email_subject"],
            "rawemail": row["raw_email"],
            "bodytext": body_text,
            "emaildate": row["email_date"].isoformat() if row["email_date"] else None,
            "createdat": row["created_at"].isoformat() if row["created_at"] else None,
            "sentat": row["sent_at"].isoformat() if row["sent_at"] else None,
            "sendstatus": row["send_status"],
            "documents": documents,

            "archived": False,
            "is_read": True,
            "prob1": None,
            "predictedclass": None,
            "modeldecision": None,
            "documentid": None,
            "type": None,
            "status": None,
            "priority": 100,
            "inputdata": {},
            "outputdata": {},
            "assignedto": None,
            "errormessage": None,
            "attempts": 0,
            "maxattempts": 0,
            "taskcreatedat": None,
            "taskstartedat": None,
            "taskcompletedat": None,
        }

        result.append(item)

    return {
        "items": result,
        "total": total,
        "page": page,
        "per_page": per_page,
    }