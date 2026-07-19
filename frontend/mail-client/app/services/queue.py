from __future__ import annotations

import json
from typing import Any
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.db import get_db_pool


def _task_status_order_sql(task_alias: str = "tt") -> str:
    return f"""
        CASE
            WHEN {task_alias}.status = 'completed' THEN 0
            WHEN {task_alias}.status = 'manual_review_done' THEN 1
            WHEN {task_alias}.status = 'ml_classified' THEN 2
            WHEN {task_alias}.status = 'materials_review' THEN 3
            WHEN {task_alias}.status = 'ml_review' THEN 4
            WHEN {task_alias}.status = 'files_saved' THEN 5
            WHEN {task_alias}.status = 'downloaded' THEN 6
            WHEN {task_alias}.status = 'new' THEN 7
            WHEN {task_alias}.status = 'error' THEN 8
            ELSE 100
        END
    """


def _map_ui_statuses_to_task_statuses(statuses: list[str]) -> list[str]:
    status_map = {
        "waiting": ["new", "downloaded", "files_saved"],
        "processing": ["ml_processing", "manual_review_done"],
        "manual_review": ["materials_review", "ml_review"],
        "completed": ["completed"],
        "error": ["error"],
    }

    mapped: list[str] = []

    for raw_status in statuses:
        status = (raw_status or "").strip().lower()
        if not status:
            continue

        mapped.extend(status_map.get(status, [status]))

    seen: set[str] = set()
    result: list[str] = []

    for item in mapped:
        if item not in seen:
            seen.add(item)
            result.append(item)

    return result


def _normalize_documents(raw: Any) -> list[dict]:
    """
    Приводим documents к виду list[dict] с полем document_name.
    Обрабатываем случаи:
    - уже list[dict]
    - jsonb -> dict/list
    - строка JSON
    - мусор — тогда возвращаем пустой список
    """
    if raw is None:
        return []

    # Если это уже list
    if isinstance(raw, list):
        # PostgreSQL jsonb_agg(jsonb_build_object(...)) обычно даёт list[dict]
        docs: list[dict] = []
        for item in raw:
            if isinstance(item, dict):
                docs.append(item)
            else:
                # если вдруг это строка JSON по одному на элемент
                try:
                    parsed = json.loads(item)
                    if isinstance(parsed, dict):
                        docs.append(parsed)
                except Exception:
                    continue
        return docs

    # Если пришла одна строка с JSON-массивом
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except Exception:
            return []

        if isinstance(parsed, list):
            return [
                d for d in parsed
                if isinstance(d, dict)
            ]
        if isinstance(parsed, dict):
            return [parsed]
        return []

    # Если это dict (один объект)
    if isinstance(raw, dict):
        return [raw]

    return []


async def list_queue_for_user(
    user: dict,
    status: str = "",
    archived: bool | None = None,
    page: int = 1,
    per_page: int = 100,
    search: str = "",
    class_filter: str = "",
    sort: str = "newest",
) -> dict[str, Any]:
    pool = await get_db_pool()

    if page < 1:
        page = 1
    if per_page < 1:
        per_page = 1
    if per_page > 100:
        per_page = 100

    offset = (page - 1) * per_page

    async with pool.acquire() as conn:
        where_clauses: list[str] = []
        params: list[object] = []
        param_idx = 1

        print("QUEUE USER =", user)
        print("QUEUE USER ROLE =", user.get("role"))
        print("QUEUE USER EMAIL =", user.get("email"))

        is_admin = user.get("role") == "admin"
        ui_statuses = [s.strip() for s in status.split(",") if s.strip()]
        statuses = _map_ui_statuses_to_task_statuses(ui_statuses)
        normalized_search = (search or "").strip().lower()
        normalized_class_filter = (class_filter or "").strip().lower()
        normalized_sort = "oldest" if (sort or "").strip().lower() == "oldest" else "newest"

        if not is_admin:
            where_clauses.append(f"e.mailbox = ${param_idx}")
            params.append(user["email"])
            param_idx += 1

        if statuses:
            where_clauses.append(f"LOWER(lt.status::text) = ANY(${param_idx}::text[])")
            params.append(statuses)
            param_idx += 1

        if archived is not None:
            where_clauses.append(f"e.archived = ${param_idx}")
            params.append(archived)
            param_idx += 1

        if normalized_search:
            where_clauses.append(
                f"""(
                    LOWER(COALESCE(e.email_subject, '')) LIKE ${param_idx}
                    OR LOWER(COALESCE(e.email_from, '')) LIKE ${param_idx}
                    OR LOWER(COALESCE(e.mailbox, '')) LIKE ${param_idx}
                    OR LOWER(COALESCE(e.raw_email, '')) LIKE ${param_idx}
                )"""
            )
            params.append(f"%{normalized_search}%")
            param_idx += 1

        if normalized_class_filter:
            if normalized_class_filter == "undefined_only":
                where_clauses.append(
                    """(
                        e.model_decision IS NULL
                        OR BTRIM(e.model_decision) = ''
                        OR LOWER(BTRIM(e.model_decision)) = 'review'
                    )"""
                )
            elif normalized_class_filter in {"request", "calculation", "question"}:
                where_clauses.append(f"LOWER(COALESCE(e.model_decision, '')) = ${param_idx}")
                params.append(normalized_class_filter)
                param_idx += 1

        where_sql = ""
        if where_clauses:
            where_sql = "\nWHERE " + "\n  AND ".join(where_clauses)

        page_order_sql = """
            sort_date DESC,
            id DESC
        """
        dedupe_pick_order_sql = """
            sort_date DESC,
            id DESC
        """

        if normalized_sort == "oldest":
            page_order_sql = """
                sort_date ASC,
                id ASC
            """
            dedupe_pick_order_sql = """
                sort_date ASC,
                id ASC
            """

        base_cte = f"""
            WITH latest_task AS (
                SELECT
                    e.id AS email_id,
                    t.id AS task_id,
                    t.status,
                    ROW_NUMBER() OVER (
                        PARTITION BY e.id
                        ORDER BY
                            {_task_status_order_sql("t")},
                            t.created_at DESC
                    ) AS rn
                FROM emails e
                LEFT JOIN tasks t
                    ON t.email_id = e.id
            ),
            filtered AS (
                SELECT
                    e.id,
                    COALESCE(e.email_date, e.created_at) AS sort_date,
                    COALESCE(NULLIF(e.message_id, ''), 'no_id_' || e.id::text) AS dedupe_key
                FROM emails e
                LEFT JOIN latest_task lt
                    ON lt.email_id = e.id
                   AND lt.rn = 1
                {where_sql}
            )
        """

        if is_admin:
            count_sql = base_cte + f"""
                , deduped AS (
                    SELECT DISTINCT ON (dedupe_key)
                        id,
                        dedupe_key,
                        sort_date
                    FROM filtered
                    ORDER BY
                        dedupe_key,
                        {dedupe_pick_order_sql}
                )
                SELECT COUNT(*) AS total
                FROM deduped
            """

            page_sql = base_cte + f"""
                , deduped AS (
                    SELECT DISTINCT ON (dedupe_key)
                        id,
                        dedupe_key,
                        sort_date
                    FROM filtered
                    ORDER BY
                        dedupe_key,
                        {dedupe_pick_order_sql}
                )
                SELECT
                    id
                FROM deduped
                ORDER BY
                    {page_order_sql}
                LIMIT ${param_idx}
                OFFSET ${param_idx + 1}
            """
        else:
            count_sql = base_cte + """
                SELECT COUNT(*) AS total
                FROM filtered
            """

            page_sql = base_cte + f"""
                SELECT
                    id
                FROM filtered
                ORDER BY
                    {page_order_sql}
                LIMIT ${param_idx}
                OFFSET ${param_idx + 1}
            """

        total_row = await conn.fetchrow(count_sql, *params)
        total = int(total_row["total"] or 0)

        page_rows = await conn.fetch(page_sql, *params, per_page, offset)
        email_ids = [row["id"] for row in page_rows]

        if not email_ids:
            total_pages = max(1, (total + per_page - 1) // per_page)

            return {
                "items": [],
                "total": total,
                "page": page,
                "per_page": per_page,
                "total_pages": total_pages,
            }

        details_sql = f"""
            SELECT
                e.id AS email_id,
                e.mailbox,
                e.email_uid,
                e.message_id,
                e.in_reply_to,
                e.references_header AS references,
                e.email_from,
                e.email_subject,
                e.raw_email,
                e.email_date,
                e.model_decision AS email_model_decision,
                e.archived AS email_archived,
                e.is_read AS email_is_read,
                e.comment_text AS email_comment_text,
                e.created_at AS email_created_at,
                e.is_primary_recipient,

                t.id AS task_id,
                t.document_id AS task_document_id,
                NULL::text AS task_type,
                t.status AS task_status,
                100 AS task_priority,
                NULL::jsonb AS input_data,
                t.output_data,
                t.assigned_to,
                t.error_message,
                t.attempts AS attempts,
                3 AS max_attempts,
                t.created_at AS task_created_at,
                NULL::timestamptz AS task_started_at,
                t.completed_at AS task_completed_at,

                COALESCE(
                    jsonb_agg(
                        DISTINCT jsonb_build_object(
                            'id', d.id,
                            'document_name', d.filename,
                            'object_bucket', NULL,
                            'object_key', d.minio_object_key,
                            'has_document_data',
                                CASE WHEN d.size_bytes IS NOT NULL AND d.size_bytes > 0 THEN true ELSE false END,
                            'result_document_name', NULL,
                            'has_result_document_data', false,
                            'created_at', d.created_at
                        )
                    ) FILTER (WHERE d.id IS NOT NULL),
                    '[]'::jsonb
                ) AS documents

            FROM emails e

            LEFT JOIN LATERAL (
                SELECT
                    tt.id,
                    tt.document_id,
                    NULL::text AS type,
                    tt.status,
                    100 AS priority,
                    NULL::jsonb AS input_data,
                    tt.output_data,
                    tt.assigned_to,
                    tt.error_message,
                    COALESCE(tt.retry_count, 0) AS attempts,
                    3 AS max_attempts,
                    tt.created_at,
                    NULL::timestamptz AS started_at,
                    tt.completed_at
                FROM tasks tt
                WHERE tt.email_id = e.id
                ORDER BY
                    {_task_status_order_sql("tt")},
                    tt.created_at DESC
                LIMIT 1
            ) t ON TRUE

            LEFT JOIN documents d
                ON d.email_id = e.id

            WHERE e.id = ANY($1::int[])

            GROUP BY
                e.id,
                t.document_id,
                e.mailbox,
                e.email_uid,
                e.email_from,
                e.email_subject,
                e.raw_email,
                e.email_date,
                e.message_id,
                e.in_reply_to,
                e.references_header,
                e.archived,
                e.is_read,
                e.comment_text,
                e.created_at,
                e.is_primary_recipient,
                t.id,
                t.status,
                t.output_data,
                t.assigned_to,
                t.error_message,
                t.attempts,
                t.created_at,
                t.completed_at
        """

        detail_rows = await conn.fetch(details_sql, email_ids)
        rows_by_id = {row["email_id"]: row for row in detail_rows}

        result: list[dict] = []

        for email_id in email_ids:
            row = rows_by_id.get(email_id)
            if not row:
                continue

            task_output = row["output_data"]

            if task_output is None:
                task_output = {}
            elif isinstance(task_output, str):
                try:
                    task_output = json.loads(task_output)
                except Exception:
                    task_output = {}

            if not isinstance(task_output, (dict, list)):
                task_output = {}

            predicted_class = None
            prob_1 = None

            if isinstance(task_output, dict):
                predicted_class = task_output.get("predicted_class")
                prob_1 = task_output.get("prob_1")

            model_decision = row["email_model_decision"]
            documents = _normalize_documents(row["documents"])

            item: dict = {
                "emailid": row["email_id"],
                "messageid": row["message_id"],
                "inreplyto": row["in_reply_to"],
                "references": row["references"],
                "mailbox": row["mailbox"],
                "emailuid": row["email_uid"],
                "emailfrom": row["email_from"],
                "emailsubject": row["email_subject"],
                "rawemail": row["raw_email"],
                "emaildate": row["email_date"].isoformat()
                if row["email_date"]
                else None,
                "createdat": row["email_created_at"].isoformat()
                if row["email_created_at"]
                else None,
                "archived": bool(row["email_archived"]),
                "is_read": bool(row["email_is_read"]),
                "comment_text": row["email_comment_text"],
                "has_comment": bool((row["email_comment_text"] or "").strip()),
                "prob1": prob_1,
                "predictedclass": predicted_class,
                "modeldecision": model_decision,
                "documents": documents,
                "is_primary_recipient": row["is_primary_recipient"],
            }

            if row["task_id"]:
                item.update(
                    {
                        "id": row["task_id"],
                        "documentid": row["task_document_id"],
                        "type": row["task_type"],
                        "status": row["task_status"],
                        "priority": row["task_priority"],
                        "inputdata": row["input_data"] or {},
                        "outputdata": task_output,
                        "assignedto": row["assigned_to"],
                        "errormessage": row["error_message"],
                        "attempts": row["attempts"],
                        "maxattempts": row["max_attempts"],
                        "taskcreatedat": row["task_created_at"].isoformat()
                        if row["task_created_at"]
                        else None,
                        "taskstartedat": row["task_started_at"].isoformat()
                        if row["task_started_at"]
                        else None,
                        "taskcompletedat": row["task_completed_at"].isoformat()
                        if row["task_completed_at"]
                        else None,
                    }
                )
            else:
                item.update(
                    {
                        "id": row["email_id"],
                        "documentid": None,
                        "type": None,
                        "status": None,
                        "priority": 100,
                        "inputdata": {},
                        "outputdata": {},
                        "assignedto": None,
                        "errormessage": None,
                        "attempts": 0,
                        "maxattempts": 3,
                        "taskcreatedat": None,
                        "taskstartedat": None,
                        "taskcompletedat": None,
                    }
                )

            result.append(item)

        total_pages = max(1, (total + per_page - 1) // per_page)

        return {
            "items": result,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
        }
    

async def get_email_detail_for_user(
    user: dict,
    email_id: int,
) -> dict[str, Any] | None:
    pool = await get_db_pool()

    async with pool.acquire() as conn:
        params: list[object] = [email_id]
        mailbox_sql = ""
        if user.get("role") != "admin":
            mailbox_sql = "AND e.mailbox = $2"
            params.append(user["email"])

        sql = f"""
            SELECT
                e.id AS email_id,
                e.mailbox,
                e.email_uid,
                e.message_id,
                e.in_reply_to,
                e.references_header AS references,
                e.email_from,
                e.email_subject,
                e.raw_email,
                e.email_date,
                e.model_decision AS email_model_decision,
                e.archived AS email_archived,
                e.is_read AS email_is_read,
                e.comment_text AS email_comment_text,
                e.created_at AS email_created_at,
                e.is_primary_recipient,

                t.id AS task_id,
                t.document_id AS task_document_id,
                NULL::text AS task_type,
                t.status AS task_status,
                100 AS task_priority,
                NULL::jsonb AS input_data,
                t.output_data,
                t.assigned_to,
                t.error_message,
                t.attempts AS attempts,
                3 AS max_attempts,
                t.created_at AS task_created_at,
                NULL::timestamptz AS task_started_at,
                t.completed_at AS task_completed_at,

                COALESCE(
                    jsonb_agg(
                        DISTINCT jsonb_build_object(
                            'id', d.id,
                            'document_name', d.filename,
                            'object_bucket', NULL,
                            'object_key', d.minio_object_key,
                            'has_document_data',
                                CASE WHEN d.size_bytes IS NOT NULL AND d.size_bytes > 0 THEN true ELSE false END,
                            'result_document_name', NULL,
                            'has_result_document_data', false,
                            'created_at', d.created_at
                        )
                    ) FILTER (WHERE d.id IS NOT NULL),
                    '[]'::jsonb
                ) AS documents

            FROM emails e

            LEFT JOIN LATERAL (
                SELECT
                    tt.id,
                    tt.document_id,
                    NULL::text AS type,
                    tt.status,
                    100 AS priority,
                    NULL::jsonb AS input_data,
                    tt.output_data,
                    tt.assigned_to,
                    tt.error_message,
                    COALESCE(tt.retry_count, 0) AS attempts,
                    3 AS max_attempts,
                    tt.created_at,
                    NULL::timestamptz AS started_at,
                    tt.completed_at
                FROM tasks tt
                WHERE tt.email_id = e.id
                ORDER BY
                    {_task_status_order_sql("tt")},
                    tt.created_at DESC
                LIMIT 1
            ) t ON TRUE

            LEFT JOIN documents d
                ON d.email_id = e.id

            WHERE e.id = $1
              {mailbox_sql}

            GROUP BY
                e.id,
                t.document_id,
                e.mailbox,
                e.email_uid,
                e.message_id,
                e.in_reply_to,
                e.references_header,
                e.email_from,
                e.email_subject,
                e.raw_email,
                e.email_date,
                e.model_decision,
                e.archived,
                e.is_read,
                e.comment_text,
                e.created_at,
                e.is_primary_recipient,
                t.id,
                t.status,
                t.output_data,
                t.assigned_to,
                t.error_message,
                t.attempts,
                t.created_at,
                t.completed_at
            LIMIT 1
        """

        row = await conn.fetchrow(sql, *params)

    if not row:
        return None

    task_output = row["output_data"]

    if task_output is None:
        task_output = {}
    elif isinstance(task_output, str):
        try:
            task_output = json.loads(task_output)
        except Exception:
            task_output = {}

    if not isinstance(task_output, (dict, list)):
        task_output = {}

    predicted_class = None
    prob_1 = None

    if isinstance(task_output, dict):
        predicted_class = task_output.get("predicted_class")
        prob_1 = task_output.get("prob_1")

    item: dict[str, Any] = {
        "emailid": row["email_id"],
        "messageid": row["message_id"],
        "inreplyto": row["in_reply_to"],
        "references": row["references"],
        "mailbox": row["mailbox"],
        "emailuid": row["email_uid"],
        "emailfrom": row["email_from"],
        "emailsubject": row["email_subject"],
        "rawemail": row["raw_email"],
        "emaildate": row["email_date"].isoformat() if row["email_date"] else None,
        "createdat": row["email_created_at"].isoformat() if row["email_created_at"] else None,
        "archived": bool(row["email_archived"]),
        "is_read": bool(row["email_is_read"]),
        "comment_text": row["email_comment_text"],
        "has_comment": bool((row["email_comment_text"] or "").strip()),
        "prob1": prob_1,
        "predictedclass": predicted_class,
        "modeldecision": row["email_model_decision"],
        "documents": _normalize_documents(row["documents"]),
        "is_primary_recipient": row["is_primary_recipient"],
    }

    if row["task_id"]:
        item.update(
            {
                "id": row["task_id"],
                "documentid": row["task_document_id"],
                "type": row["task_type"],
                "status": row["task_status"],
                "priority": row["task_priority"],
                "inputdata": row["input_data"] or {},
                "outputdata": task_output,
                "assignedto": row["assigned_to"],
                "errormessage": row["error_message"],
                "attempts": row["attempts"],
                "maxattempts": row["max_attempts"],
                "taskcreatedat": row["task_created_at"].isoformat() if row["task_created_at"] else None,
                "taskstartedat": row["task_started_at"].isoformat() if row["task_started_at"] else None,
                "taskcompletedat": row["task_completed_at"].isoformat() if row["task_completed_at"] else None,
            }
        )
    else:
        item.update(
            {
                "id": row["email_id"],
                "documentid": None,
                "type": None,
                "status": None,
                "priority": 100,
                "inputdata": {},
                "outputdata": {},
                "assignedto": None,
                "errormessage": None,
                "attempts": 0,
                "maxattempts": 3,
                "taskcreatedat": None,
                "taskstartedat": None,
                "taskcompletedat": None,
            }
        )

    return item


NOVOSIBIRSK_TZ = ZoneInfo("Asia/Novosibirsk")


def _order_thread_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not items:
        return []

    by_message_id: dict[str, dict[str, Any]] = {}
    children_map: dict[str, list[dict[str, Any]]] = {}
    roots: list[dict[str, Any]] = []

    for item in items:
        msg_id = _normalize_message_id(item.get("message_id"))
        if msg_id:
            by_message_id[msg_id] = item

    for item in items:
        parent_id = _normalize_message_id(item.get("in_reply_to"))
        if parent_id and parent_id in by_message_id:
            children_map.setdefault(parent_id, []).append(item)
        else:
            roots.append(item)

    for child_list in children_map.values():
        child_list.sort(key=_thread_sort_dt)

    roots.sort(key=_thread_sort_dt)

    ordered: list[dict[str, Any]] = []
    visited: set[tuple[str, int]] = set()

    def walk(node: dict[str, Any]) -> None:
        node_key = (str(node.get("thread_source")), int(node.get("source_id")))
        if node_key in visited:
            return
        visited.add(node_key)
        ordered.append(node)

        node_msg_id = _normalize_message_id(node.get("message_id"))
        if not node_msg_id:
            return

        for child in children_map.get(node_msg_id, []):
            walk(child)

    for root in roots:
        walk(root)

    remaining = [item for item in items if (str(item.get("thread_source")), int(item.get("source_id"))) not in visited]
    remaining.sort(key=_thread_sort_dt)
    ordered.extend(remaining)

    return ordered


def _to_novosibirsk_iso(dt) -> str | None:
    if not dt:
        return None
    return dt.astimezone(NOVOSIBIRSK_TZ).isoformat()


def _parse_sort_dt(raw: str | None) -> datetime:
    if not raw:
        return datetime.min.replace(tzinfo=NOVOSIBIRSK_TZ)
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=NOVOSIBIRSK_TZ)
        return dt.astimezone(NOVOSIBIRSK_TZ)
    except Exception:
        return datetime.min.replace(tzinfo=NOVOSIBIRSK_TZ)
    

MESSAGE_ID_RE = re.compile(
    r'<?\[?(?P<id>[^\s<>()[\]]+@[^\s<>()[\]]+)\]?>?',
    re.IGNORECASE,
)


def _extract_message_ids(value: Any) -> set[str]:
    if not value:
        return set()

    text = str(value)
    ids: set[str] = set()

    for token in re.split(r'[\s,]+', text):
        norm = _normalize_message_id(token)
        if norm:
            ids.add(norm)

    return ids


def _normalize_message_id(value: Any) -> str | None:
    if not value:
        return None

    text = str(value)

    match = MESSAGE_ID_RE.search(text)
    if not match:
        return None

    msg_id = match.group("id").strip()

    return msg_id or None


def _collect_thread_keys(item: dict[str, Any]) -> set[str]:
    keys: set[str] = set()

    message_id = _normalize_message_id(item.get("message_id"))
    in_reply_to = _normalize_message_id(item.get("in_reply_to"))
    references = _extract_message_ids(item.get("references"))

    if message_id:
        keys.add(message_id)
    if in_reply_to:
        keys.add(in_reply_to)
    keys.update(references)

    return keys


def _item_matches_thread(item: dict[str, Any], thread_keys: set[str]) -> bool:
    if not thread_keys:
        return False

    message_id = _normalize_message_id(item.get("message_id"))
    in_reply_to = _normalize_message_id(item.get("in_reply_to"))
    references = _extract_message_ids(item.get("references"))

    print("MATCH DEBUG item:", item.get("thread_source"), item.get("source_id"),
          "message_id=", message_id,
          "in_reply_to=", in_reply_to,
          "references=", references,
          "thread_keys=", thread_keys)

    if message_id and message_id in thread_keys:
        return True
    if in_reply_to and in_reply_to in thread_keys:
        return True
    if any(ref in thread_keys for ref in references):
        return True

    return False


def _thread_sort_dt(item: dict[str, Any]) -> tuple[datetime, int]:
    raw = item.get("emaildate") or item.get("createdat") or item.get("sentat")
    dt = _parse_sort_dt(raw)
    return (dt, int(item.get("id") or item.get("source_id") or 0))


async def get_email_thread_for_user(
    user: dict,
    email_id: int,
    source: str | None = None,
) -> dict[str, Any]:
    pool = await get_db_pool()

    async with pool.acquire() as conn:
        is_admin = user.get("role") == "admin"

        if source == "sent":
            if is_admin:
                root_email = await conn.fetchrow(
                    """
                    SELECT
                        'sent'::text AS source_type,
                        se.id AS source_id,
                        se.parent_email_id AS email_id,
                        se.mailbox,
                        se.message_id,
                        se.in_reply_to,
                        se.references_header
                    FROM sent_emails se
                    WHERE se.id = $1
                    LIMIT 1
                    """,
                    email_id,
                )
            else:
                root_email = await conn.fetchrow(
                    """
                    SELECT
                        'sent'::text AS source_type,
                        se.id AS source_id,
                        se.parent_email_id AS email_id,
                        se.mailbox,
                        se.message_id,
                        se.in_reply_to,
                        se.references_header
                    FROM sent_emails se
                    WHERE se.id = $1
                      AND se.mailbox = $2
                    LIMIT 1
                    """,
                    email_id,
                    user["email"],
                )

        elif source == "inbox":
            if is_admin:
                root_email = await conn.fetchrow(
                    """
                    SELECT
                        'inbox'::text AS source_type,
                        e.id AS source_id,
                        e.id AS email_id,
                        e.mailbox,
                        e.message_id,
                        e.in_reply_to,
                        e.references_header
                    FROM emails e
                    WHERE e.id = $1
                    LIMIT 1
                    """,
                    email_id,
                )
            else:
                root_email = await conn.fetchrow(
                    """
                    SELECT
                        'inbox'::text AS source_type,
                        e.id AS source_id,
                        e.id AS email_id,
                        e.mailbox,
                        e.message_id,
                        e.in_reply_to,
                        e.references_header
                    FROM emails e
                    WHERE e.id = $1
                      AND e.mailbox = $2
                    LIMIT 1
                    """,
                    email_id,
                    user["email"],
                )

        if not root_email:
            return {
                "items": [],
                "count": 0,
            }

        mailbox = root_email["mailbox"]

        inbox_rows = await conn.fetch(
            """
            SELECT
                e.id AS source_id,
                'inbox'::text AS source_type,
                e.id AS email_id,
                e.mailbox,
                e.email_uid,
                e.message_id,
                e.in_reply_to,
                e.references_header AS references,
                e.email_from,
                e.reply_to,
                e.to_header,
                e.cc_header,
                e.email_subject,
                e.raw_email,
                e.email_date,
                e.model_decision AS email_model_decision,
                e.archived AS email_archived,
                e.is_read AS email_is_read,
                e.created_at AS email_created_at,
                e.is_primary_recipient,

                t.id AS task_id,
                t.document_id AS task_document_id,
                NULL::text AS task_type,
                t.status AS task_status,
                100 AS task_priority,
                NULL::jsonb AS input_data,
                t.output_data,
                t.assigned_to,
                t.error_message,
                COALESCE(t.attempts, 0) AS attempts,
                3 AS max_attempts,
                t.created_at AS task_created_at,
                NULL::timestamptz AS task_started_at,
                t.completed_at AS task_completed_at,

                COALESCE(
                    jsonb_agg(
                        DISTINCT jsonb_build_object(
                            'id', d.id,
                            'document_name', d.filename,
                            'object_bucket', NULL,
                            'object_key', d.minio_object_key,
                            'has_document_data',
                                CASE WHEN d.size_bytes IS NOT NULL AND d.size_bytes > 0 THEN true ELSE false END,
                            'result_document_name', NULL,
                            'has_result_document_data', false,
                            'created_at', d.created_at
                        )
                    ) FILTER (WHERE d.id IS NOT NULL),
                    '[]'::jsonb
                ) AS documents
            FROM emails e
            LEFT JOIN LATERAL (
                SELECT
                    tt.id,
                    tt.document_id,
                    NULL::text AS type,
                    tt.status,
                    100 AS priority,
                    NULL::jsonb AS input_data,
                    tt.output_data,
                    tt.assigned_to,
                    tt.error_message,
                    COALESCE(tt.retry_count, 0) AS attempts,
                    3 AS max_attempts,
                    tt.created_at,
                    NULL::timestamptz AS started_at,
                    tt.completed_at
                FROM tasks tt
                WHERE tt.email_id = e.id
                ORDER BY
                    CASE
                        WHEN tt.status = 'completed' THEN 0
                        WHEN tt.status = 'manual_review_done' THEN 1
                        WHEN tt.status = 'ml_classified' THEN 2
                        WHEN tt.status = 'materials_review' THEN 3
                        WHEN tt.status = 'ml_review' THEN 4
                        WHEN tt.status = 'files_saved' THEN 5
                        WHEN tt.status = 'downloaded' THEN 6
                        WHEN tt.status = 'new' THEN 7
                        WHEN tt.status = 'error' THEN 8
                        ELSE 100
                    END,
                    tt.created_at DESC
                LIMIT 1
            ) t ON TRUE
            LEFT JOIN documents d
                ON d.email_id = e.id
            WHERE e.mailbox = $1
            GROUP BY
                e.id,
                e.mailbox,
                e.email_uid,
                e.message_id,
                e.in_reply_to,
                e.references_header,
                e.email_from,
                e.reply_to,
                e.to_header,
                e.cc_header,
                e.email_subject,
                e.raw_email,
                e.email_date,
                e.model_decision,
                e.archived,
                e.is_read,
                e.created_at,
                e.is_primary_recipient,
                t.id,
                t.document_id,
                t.status,
                t.output_data,
                t.assigned_to,
                t.error_message,
                t.attempts,
                t.created_at,
                t.completed_at
            """,
            mailbox,
        )

        sent_rows = await conn.fetch(
            """
            SELECT
                se.id AS source_id,
                'sent'::text AS source_type,
                se.parent_email_id AS email_id,
                se.mailbox,
                se.email_uid,
                se.message_id,
                se.in_reply_to,
                se.references_header AS references,
                se.email_from,
                se.reply_to,
                se.to_header,
                se.cc_header,
                se.email_subject,
                se.raw_email,
                se.sent_at AS email_date,
                'sent'::text AS email_model_decision,
                false AS email_archived,
                true AS email_is_read,
                se.created_at AS email_created_at,
                false AS is_primary_recipient,

                NULL::bigint AS task_id,
                NULL::bigint AS task_document_id,
                NULL::text AS task_type,
                NULL::task_status AS task_status,
                100 AS task_priority,
                NULL::jsonb AS input_data,
                NULL::jsonb AS output_data,
                NULL::bigint AS assigned_to,
                NULL::text AS error_message,
                0 AS attempts,
                3 AS max_attempts,
                NULL::timestamptz AS task_created_at,
                NULL::timestamptz AS task_started_at,
                NULL::timestamptz AS task_completed_at,

                COALESCE(
                    jsonb_agg(
                        DISTINCT jsonb_build_object(
                            'id', sd.id,
                            'document_name', sd.filename,
                            'object_bucket', NULL,
                            'object_key', sd.minio_object_key,
                            'has_document_data',
                                CASE WHEN sd.size_bytes IS NOT NULL AND sd.size_bytes > 0 THEN true ELSE false END,
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
            WHERE se.mailbox = $1
            GROUP BY
                se.id,
                se.parent_email_id,
                se.mailbox,
                se.email_uid,
                se.message_id,
                se.in_reply_to,
                se.references_header,
                se.email_from,
                se.reply_to,
                se.to_header,
                se.cc_header,
                se.email_subject,
                se.raw_email,
                se.sent_at,
                se.created_at
            """,
            mailbox,
        )

    candidates: list[dict[str, Any]] = []

    for row in inbox_rows:
        task_output = row["output_data"]
        if task_output is None:
            task_output = {}
        elif isinstance(task_output, str):
            try:
                task_output = json.loads(task_output)
            except Exception:
                task_output = {}

        if not isinstance(task_output, (dict, list)):
            task_output = {}

        predicted_class = None
        prob_1 = None
        if isinstance(task_output, dict):
            predicted_class = task_output.get("predicted_class")
            prob_1 = task_output.get("prob_1")

        item = {
            "thread_source": row["source_type"],
            "source_id": row["source_id"],
            "emailid": row["email_id"],
            "messageid": row["message_id"],
            "inreplyto": row["in_reply_to"],
            "references": row["references"],
            "mailbox": row["mailbox"],
            "emailuid": row["email_uid"],
            "emailfrom": row["email_from"],
            "replyto": row["reply_to"],
            "toheader": row["to_header"],
            "ccheader": row["cc_header"],
            "emailsubject": row["email_subject"],
            "rawemail": row["raw_email"],
            "emaildate": row["email_date"].isoformat() if row["email_date"] else None,
            "createdat": row["email_created_at"].isoformat() if row["email_created_at"] else None,
            "archived": bool(row["email_archived"]),
            "is_read": bool(row["email_is_read"]),
            "prob1": prob_1,
            "predictedclass": predicted_class,
            "modeldecision": row["email_model_decision"],
            "documents": _normalize_documents(row["documents"]),
            "is_primary_recipient": row["is_primary_recipient"],
            "message_id": row["message_id"],
            "in_reply_to": row["in_reply_to"],
        }

        if row["task_id"]:
            item.update(
                {
                    "id": row["task_id"],
                    "documentid": row["task_document_id"],
                    "type": row["task_type"],
                    "status": row["task_status"],
                    "priority": row["task_priority"],
                    "inputdata": row["input_data"] or {},
                    "outputdata": task_output,
                    "assignedto": row["assigned_to"],
                    "errormessage": row["error_message"],
                    "attempts": row["attempts"],
                    "maxattempts": row["max_attempts"],
                    "taskcreatedat": row["task_created_at"].isoformat() if row["task_created_at"] else None,
                    "taskstartedat": row["task_started_at"].isoformat() if row["task_started_at"] else None,
                    "taskcompletedat": row["task_completed_at"].isoformat() if row["task_completed_at"] else None,
                }
            )
        else:
            item.update(
                {
                    "id": row["email_id"],
                    "documentid": None,
                    "type": None,
                    "status": None,
                    "priority": 100,
                    "inputdata": {},
                    "outputdata": {},
                    "assignedto": None,
                    "errormessage": None,
                    "attempts": 0,
                    "maxattempts": 3,
                    "taskcreatedat": None,
                    "taskstartedat": None,
                    "taskcompletedat": None,
                }
            )

        candidates.append(item)

    for row in sent_rows:
        item = {
            "thread_source": row["source_type"],
            "source_id": row["source_id"],
            "emailid": row["email_id"],
            "messageid": row["message_id"],
            "inreplyto": row["in_reply_to"],
            "references": row["references"],
            "mailbox": row["mailbox"],
            "emailuid": row["email_uid"],
            "emailfrom": row["email_from"],
            "replyto": row["reply_to"],
            "toheader": row["to_header"],
            "ccheader": row["cc_header"],
            "emailsubject": row["email_subject"],
            "rawemail": row["raw_email"],
            "emaildate": _to_novosibirsk_iso(row["email_created_at"]),
            "createdat": _to_novosibirsk_iso(row["email_created_at"]),
            "sentat": _to_novosibirsk_iso(row["email_date"]),
            "archived": False,
            "is_read": True,
            "prob1": None,
            "predictedclass": None,
            "modeldecision": "sent",
            "documents": _normalize_documents(row["documents"]),
            "is_primary_recipient": False,
            "message_id": row["message_id"],
            "in_reply_to": row["in_reply_to"],
            "id": row["source_id"],
            "documentid": None,
            "type": None,
            "status": "sent",
            "priority": 100,
            "inputdata": {},
            "outputdata": {},
            "assignedto": None,
            "errormessage": None,
            "attempts": 0,
            "maxattempts": 3,
            "taskcreatedat": None,
            "taskstartedat": None,
            "taskcompletedat": None,
        }
        candidates.append(item)

    root_source_type = str(root_email["source_type"])
    root_source_id = int(root_email["source_id"])

    root_candidate = next(
        (
            item for item in candidates
            if str(item.get("thread_source")) == root_source_type
            and int(item.get("source_id")) == root_source_id
        ),
        None,
    )
    if not root_candidate:
        return {
            "items": [],
            "count": 0,
        }

    thread_keys = _collect_thread_keys(root_candidate)
    if not thread_keys and root_candidate.get("messageid"):
        thread_keys.add(root_candidate["messageid"])

    matched_keys: set[tuple[str, int]] = set()
    related: list[dict[str, Any]] = []

    root_key = (
        str(root_candidate.get("thread_source")),
        int(root_candidate.get("source_id")),
    )
    matched_keys.add(root_key)
    related.append(root_candidate)
    thread_keys.update(_collect_thread_keys(root_candidate))

    changed = True
    while changed:
        changed = False
        for item in candidates:
            item_key = (str(item.get("thread_source")), int(item.get("source_id")))
            if item_key in matched_keys:
                continue
            if _item_matches_thread(item, thread_keys):
                print("THREAD DEBUG matched item:", item.get("thread_source"), item.get("source_id"),
                      "message_id=", item.get("messageid"),
                      "in_reply_to=", item.get("in_reply_to"),
                      "references=", item.get("references"))
                matched_keys.add(item_key)
                related.append(item)
                before = len(thread_keys)
                thread_keys.update(_collect_thread_keys(item))
                if len(thread_keys) > before:
                    changed = True

    related = _order_thread_items(related)

    return {
        "items": related,
        "count": len(related),
    }