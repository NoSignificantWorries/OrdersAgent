from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from app.db import get_db_pool
from app.routers import auth
from app.services.queue import list_queue_for_user


router = APIRouter(prefix="/api", tags=["queue"])


class DecisionUpdate(BaseModel):
    predicted_class: int | None = None
    model_decision: str | None = None


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


@router.post("/queue/{item_id}/decision")
async def update_queue_decision(
    item_id: int,
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
        if user.get("role") == "admin":
            row = await conn.fetchrow(
                """
                SELECT id, email_uid
                FROM process_queue
                WHERE id = $1
                """,
                item_id,
            )
        else:
            row = await conn.fetchrow(
                """
                SELECT id, email_uid
                FROM process_queue
                WHERE id = $1 AND target_user_id = $2
                """,
                item_id,
                user["id"],
            )

        if not row:
            raise HTTPException(status_code=404, detail="Запись не найдена")

        email_uid = row["email_uid"]
        if not email_uid:
            raise HTTPException(status_code=400, detail="У записи отсутствует email_uid")

        fields = []
        values = []

        if payload.predicted_class is not None:
            fields.append(f"predicted_class = ${len(values) + 1}")
            values.append(payload.predicted_class)

        if payload.model_decision is not None:
            fields.append(f"model_decision = ${len(values) + 1}")
            values.append(payload.model_decision)

            if payload.model_decision in ("auto_0", "auto_1"):
                fields.append(f"status = ${len(values) + 1}")
                values.append("clarification")
            elif payload.model_decision == "review":
                fields.append(f"status = ${len(values) + 1}")
                values.append("review")

        values.append(email_uid)

        if user.get("role") == "admin":
            sql = f"""
                UPDATE process_queue
                SET {", ".join(fields)}
                WHERE email_uid = ${len(values)}
            """
        else:
            values.append(user["id"])
            sql = f"""
                UPDATE process_queue
                SET {", ".join(fields)}
                WHERE email_uid = ${len(values) - 1}
                  AND target_user_id = ${len(values)}
            """

        result = await conn.execute(sql, *values)

    return {
        "ok": True,
        "id": item_id,
        "email_uid": email_uid,
        "updated": result,
    }