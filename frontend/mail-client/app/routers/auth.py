# app/routers/auth.py
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
import httpx
import secrets
from urllib.parse import urlencode

from app.config import settings
from app.services.users import (
    get_or_create_user_by_email,
    update_user_mail_tokens,
)

router = APIRouter()

# Простое хранилище сессий (в памяти)
sessions = {}


def generate_state():
    """Генерация случайного state для защиты от CSRF"""
    return secrets.token_urlsafe(32)


@router.get("/auth/yandex")
async def auth_yandex(request: Request):
    """Начало авторизации через Яндекс (с правами на почту)"""
    state = generate_state()

    use_secure_cookies = request.url.scheme == "https"

    scope = "login:email login:info mail:imap_full mail:smtp"

    params = {
        "response_type": "code",
        "client_id": settings.yandex_client_id,
        "redirect_uri": settings.yandex_redirect_uri,
        "state": state,
        "scope": scope,
        "force_confirm": "yes",
    }

    auth_url = f"{settings.yandex_auth_url}?{urlencode(params)}"
    response = RedirectResponse(url=auth_url)

    response.set_cookie(
        key="oauth_state",
        value=state,
        httponly=True,
        max_age=300,
        samesite="lax",
        secure=use_secure_cookies,
        path="/",
    )

    print("OAuth authorization started")

    return response


@router.get("/callback")
async def auth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    """Обработка callback от Яндекса"""
    use_secure_cookies = request.url.scheme == "https"

    print("OAuth callback received")

    if error:
        print(f"Yandex OAuth returned error: {error}")
        return RedirectResponse(url="/login", status_code=302)

    if not code:
        return RedirectResponse(url="/login", status_code=302)

    cookie_state = request.cookies.get("oauth_state")

    if not state or not cookie_state or state != cookie_state:
        print("OAuth state validation failed")
        return RedirectResponse(url="/login", status_code=302)

    print("OAuth state validated")

    async with httpx.AsyncClient(timeout=20.0) as client:
        print("Requesting Yandex OAuth token")

        token_response = await client.post(
            settings.yandex_token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": settings.yandex_client_id,
                "client_secret": settings.yandex_client_secret,
            },
        )

        print(f"Статус ответа токена: {token_response.status_code}")

        if token_response.status_code != 200:
            print(
                f"Yandex token request failed: "
                f"status={token_response.status_code}"
            )
            return RedirectResponse(url="/login", status_code=302)

        token_data = token_response.json()
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = int(token_data.get("expires_in") or 0)

        if not access_token:
            print("Yandex token response does not contain access_token")
            return RedirectResponse(url="/login", status_code=302)

        if not refresh_token:
            print("Yandex token response does not contain refresh_token")

        access_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in or 3600)

        print("Yandex OAuth token received")

        print("Requesting Yandex user info")
        user_response = await client.get(
            settings.yandex_user_info_url,
            params={"format": "json"},
            headers={"Authorization": f"OAuth {access_token}"},
        )

        if user_response.status_code != 200:
            print(
                f"Yandex user info request failed: "
                f"status={user_response.status_code}"
            )
            return RedirectResponse(url="/login", status_code=302)

        user_data = user_response.json()
        print("Yandex user info received")

        email = user_data.get("default_email")
        login = user_data.get("login") or email
        name = user_data.get("real_name") or user_data.get("display_name")

        if not email:
            print("Нет default_email у пользователя Яндекс")
            return {"error": "No default_email in Yandex user info"}

        try:
            db_user = await get_or_create_user_by_email(
                email=email,
                login=login,
                name=name,
            )
        except Exception as e:
            print(f"Failed to sync user with database: {type(e).__name__}: {e}")
            return RedirectResponse(url="/login", status_code=302)

        try:
            await update_user_mail_tokens(
                user_id=db_user["id"],
                access_token=access_token,
                refresh_token=refresh_token,
                access_expires_at=access_expires_at,
            )
            print(f"Mail tokens saved for user_id={db_user['id']}")
        except Exception as e:
            print(f"Failed to sync user with database: {type(e).__name__}: {e}")
            return RedirectResponse(url="/login", status_code=302)

        session_id = generate_state()
        sessions[session_id] = {
            "id": db_user["id"],
            "email": db_user["email"],
            "name": name,
            "login": db_user["login"],
            "role": db_user["role"],
        }

        print(f"Application session created for user_id={db_user['id']}")

        print("Перенаправляем на главную страницу...")
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            max_age=86400,
            samesite="lax",
            secure=use_secure_cookies,
            path="/",
        )

        response.delete_cookie(
            key="oauth_state",
            path="/",
            samesite="lax",
            secure=use_secure_cookies,
        )

        print("=== КОНЕЦ CALLBACK ===\n")
        return response


@router.get("/logout")
async def logout(request: Request):
    """Выход из системы"""
    session_id = request.cookies.get("session_id")

    if session_id:
        sessions.pop(session_id, None)

    use_secure_cookies = request.url.scheme == "https"

    response = RedirectResponse(url="/login", status_code=303)

    response.delete_cookie(
        key="session_id",
        path="/",
        samesite="lax",
        secure=use_secure_cookies,
    )
    return response


def get_current_user(request: Request):
    """Получение текущего пользователя из сессии"""
    session_id = request.cookies.get("session_id")

    if session_id:
        user = sessions.get(session_id)
        if user:
            return user

    return None