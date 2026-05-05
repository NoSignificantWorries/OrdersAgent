from app.db import get_db_pool


async def list_queue_for_user(user: dict, status: str = "", limit: int | None = None) -> list[dict]:
    pool = await get_db_pool()

    async with pool.acquire() as conn:
        # admin видит всё
        if user.get("role") == "admin":
            rows = await conn.fetch(
                """
                SELECT
                    id,
                    assigned_to,
                    target_user_id,
                    email_subject,
                    email_body,
                    email_uid,
                    email_from,
                    email_date,
                    document_name,
                    status,
                    prob_1,
                    predicted_class,
                    model_decision,
                    created_at
                FROM process_queue
                WHERE ($1 = '' OR status = $1)
                ORDER BY created_at DESC
                LIMIT $2
                """,
                status,
                limit,
            )
        else:
            # manager видит только свои письма
            rows = await conn.fetch(
                """
                SELECT
                    id,
                    assigned_to,
                    target_user_id,
                    email_subject,
                    email_body,
                    email_uid,
                    email_from,
                    email_date,
                    document_name,
                    status,
                    prob_1,
                    predicted_class,
                    model_decision,
                    created_at
                FROM process_queue
                WHERE target_user_id = $1
                  AND ($2 = '' OR status = $2)
                ORDER BY created_at DESC
                LIMIT $3
                """,
                user["id"],
                status,
                limit,
            )

        result = []
        for row in rows:
            result.append({
                "id": row["id"],
                "assigned_to": row["assigned_to"],
                "target_user_id": row["target_user_id"],
                "email_subject": row["email_subject"],
                "email_body": row["email_body"],
                "email_uid": row["email_uid"],
                "email_from": row["email_from"],
                "email_date": row["email_date"].isoformat() if row["email_date"] else None,
                "document_name": row["document_name"],
                "status": row["status"],
                "prob_1": row["prob_1"],
                "predicted_class": row["predicted_class"],
                "model_decision": row["model_decision"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            })

        return result