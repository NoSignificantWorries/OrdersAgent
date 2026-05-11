import json

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from app.db import get_db_pool
from app.routers import auth
from app.services.queue import list_queue_for_user


router = APIRouter(prefix="/api", tags=["queue"])


class DecisionUpdate(BaseModel):
    predicted_class: int | None = None
    model_decision: str | None = None

class MaterialsManualDecisionUpdate(BaseModel):
    manual_decision: dict[str, list]


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

            current_status = task_row["status"]
            if current_status != "ml_review":
                raise HTTPException(
                    status_code=400,
                    detail=f"Ручное решение нельзя применить для статуса {current_status}",
                )

            model_decision = payload.model_decision
            predicted_class = payload.predicted_class

            if predicted_class is None:
                if model_decision == "auto_0":
                    predicted_class = 0
                elif model_decision == "auto_1":
                    predicted_class = 1
                elif model_decision == "review":
                    predicted_class = None

            if model_decision not in {"auto_0", "auto_1"}:
                raise HTTPException(
                    status_code=400,
                    detail="Нужно выбрать итоговый класс: 'Заявка' или 'Расчёт'"
                )

            if predicted_class not in {0, 1}:
                raise HTTPException(
                    status_code=400,
                    detail="Итоговый класс должен быть 0 или 1"
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
                    status = 'ml_classified'::task_status,
                    assigned_to = $2,
                    completed_at = NOW()
                WHERE id = $3
                RETURNING
                    id,
                    email_id,
                    status,
                    assigned_to,
                    output_data,
                    completed_at
                """,
                json.dumps(output_patch),
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

            output_patch = {
                "manual_decision": normalized_manual_decision,
                "manual_updated_by": user["id"],
                "manual_review": True,
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