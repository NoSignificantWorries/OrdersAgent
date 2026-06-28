from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.routers import auth
from app.services.users import get_user_signature, update_user_signature


router = APIRouter(prefix="/api/me", tags=["me"])


class SignaturePayload(BaseModel):
    signature: str


@router.get("/signature")
async def get_my_signature(request: Request):
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    signature = await get_user_signature(user["id"])
    return {"signature": signature or ""}


@router.put("/signature")
async def put_my_signature(payload: SignaturePayload, request: Request):
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    signature = (payload.signature or "").strip()

    if len(signature) > 10000:
        raise HTTPException(status_code=400, detail="Подпись слишком длинная")

    saved = await update_user_signature(
        user_id=user["id"],
        signature=signature,
    )

    return {
        "ok": True,
        "signature": saved or "",
    }