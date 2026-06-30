from __future__ import annotations

import json
from typing import Any

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