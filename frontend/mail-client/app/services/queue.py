from __future__ import annotations

import json
from typing import Any

from app.db import get_db_pool


def _task_status_order_sql() -> str:
    return """
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
        END
    """


def _normalize_documents(raw: Any) -> list[dict]:
    if raw is None:
        return []
    if isinstance(raw, list):
        docs: list[dict] = []
        for item in raw:
            if isinstance(item, dict):
                docs.append(item)
            else:
                try:
                    parsed = json.loads(item)
                    if isinstance(parsed, dict):
                        docs.append(parsed)
                except Exception:
                    continue
        return docs
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except Exception:
            return []
        if isinstance(parsed, list):
            return [d for d in parsed if isinstance(d, dict)]
        if isinstance(parsed, dict):
            return [parsed]
        return []
    if isinstance(raw, dict):
        return [raw]
    return []


async def list_queue_for_user(
    user: dict,
    status: str = "",
    limit: int | None = None,
    offset: int = 0,
    archived: bool | None = None,
    class_filter: str = "",
) -> tuple[list[dict], int]:
    pool = await get_db_pool()

    if limit is None or limit < 1:
        limit = 100
    if limit > 500:
        limit = 500

    async with pool.acquire() as conn:
        is_admin = user.get("role") == "admin"

        # ===== ОСНОВНОЙ ЗАПРОС (с OFFSET и LIMIT) =====
        # Используем DISTINCT ON для дедупликации по message_id (для админа)
        distinct_clause = "DISTINCT ON (e.message_id)" if is_admin else ""

        sql = f"""
            SELECT {distinct_clause}
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
                    {_task_status_order_sql()},
                    tt.created_at DESC
                LIMIT 1
            ) t ON TRUE

            LEFT JOIN documents d
                ON d.email_id = e.id
        """

        where_clauses: list[str] = []
        params: list[object] = []
        param_idx = 1

        # ===== ФИЛЬТРЫ =====
        # Админ: только основные получатели, остальные пользователи: только свои письма
        if is_admin:
            where_clauses.append("e.is_primary_recipient = true")
        else:
            where_clauses.append(f"e.mailbox = ${param_idx}")
            params.append(user["email"])
            param_idx += 1

        # Фильтр по статусу (с маппингом)
        if status:
            raw_statuses = [s.strip() for s in status.split(",") if s.strip()]
            status_mapping = {
                "waiting": ["new", "downloaded", "files_saved"],
                "processing": ["ml_classified", "manual_review_done"],
                "materials_review": ["materials_review"],
                "ml_review": ["ml_review"],
                "completed": ["completed"],
                "error": ["error"],
                "manual_review": ["materials_review", "ml_review"],
                "question": ["question"],
            }
            db_statuses = []
            for s in raw_statuses:
                if s in status_mapping:
                    db_statuses.extend(status_mapping[s])
                else:
                    db_statuses.append(s)
            db_statuses = list(set(db_statuses))
            if db_statuses:
                where_clauses.append(
                    f"t.status = ANY(${param_idx}::task_status[])"
                )
                params.append(db_statuses)
                param_idx += 1

        # Фильтр по архиву
        if archived is not None:
            where_clauses.append(f"e.archived = ${param_idx}")
            params.append(archived)
            param_idx += 1

        # Фильтр по классу
        if class_filter:
            if class_filter == "undefined_only":
                where_clauses.append(
                    "(e.model_decision IS NULL OR e.model_decision = '' OR e.model_decision = 'review')"
                )
            else:
                where_clauses.append(f"e.model_decision = ${param_idx}")
                params.append(class_filter)
                param_idx += 1

        if where_clauses:
            sql += "\nWHERE " + "\n  AND ".join(where_clauses)

        # GROUP BY и ORDER BY (с учётом DISTINCT ON)
        sql += f"""
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
            ORDER BY
                e.message_id,
                COALESCE(t.created_at, e.created_at) DESC,
                e.id DESC
            OFFSET ${param_idx}
            LIMIT ${param_idx + 1}
        """
        params.append(offset)
        params.append(limit)

        rows = await conn.fetch(sql, *params)

        # ===== ЗАПРОС ДЛЯ COUNT(*) =====
        count_sql = f"""
            SELECT COUNT({ "DISTINCT e.message_id" if is_admin else "*" }) AS total
            FROM emails e
            LEFT JOIN LATERAL (
                SELECT
                    tt.id,
                    tt.status
                FROM tasks tt
                WHERE tt.email_id = e.id
                ORDER BY
                    {_task_status_order_sql()},
                    tt.created_at DESC
                LIMIT 1
            ) t ON TRUE
        """
        count_params: list[object] = []
        count_idx = 1

        # Повторяем условия WHERE (без OFFSET/LIMIT)
        if is_admin:
            count_sql += " WHERE e.is_primary_recipient = true"
        else:
            count_sql += f" WHERE e.mailbox = ${count_idx}"
            count_params.append(user["email"])
            count_idx += 1

        if status:
            raw_statuses = [s.strip() for s in status.split(",") if s.strip()]
            status_mapping = {
                "waiting": ["new", "downloaded", "files_saved"],
                "processing": ["ml_classified", "manual_review_done"],
                "materials_review": ["materials_review"],
                "ml_review": ["ml_review"],
                "completed": ["completed"],
                "error": ["error"],
                "manual_review": ["materials_review", "ml_review"],
                "question": ["question"],
            }
            db_statuses = []
            for s in raw_statuses:
                if s in status_mapping:
                    db_statuses.extend(status_mapping[s])
                else:
                    db_statuses.append(s)
            db_statuses = list(set(db_statuses))
            if db_statuses:
                count_sql += f" AND t.status = ANY(${count_idx}::task_status[])"
                count_params.append(db_statuses)
                count_idx += 1

        if archived is not None:
            count_sql += f" AND e.archived = ${count_idx}"
            count_params.append(archived)
            count_idx += 1

        if class_filter:
            if class_filter == "undefined_only":
                count_sql += " AND (e.model_decision IS NULL OR e.model_decision = '' OR e.model_decision = 'review')"
            else:
                count_sql += f" AND e.model_decision = ${count_idx}"
                count_params.append(class_filter)
                count_idx += 1

        total_row = await conn.fetchrow(count_sql, *count_params)
        total = total_row["total"] if total_row else 0

        # ===== ФОРМИРОВАНИЕ РЕЗУЛЬТАТА =====
        result: list[dict] = []

        for row in rows:
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
                "emaildate": row["email_date"].isoformat() if row["email_date"] else None,
                "createdat": row["email_created_at"].isoformat() if row["email_created_at"] else None,
                "archived": bool(row["email_archived"]),
                "is_read": bool(row["email_is_read"]),
                "prob1": prob_1,
                "predictedclass": predicted_class,
                "modeldecision": model_decision,
                "documents": documents,
                "is_primary_recipient": row["is_primary_recipient"],
            }

            if row["task_id"]:
                item.update({
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
                })
            else:
                item.update({
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
                })

            result.append(item)

        return result, total