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
    update_user_mail_tokens,  # <-- нужно добавить в app/services/users.py
)

router = APIRouter()

# Простое хранилище сессий (в памяти)
sessions = {}


def generate_state():
    """Генерация случайного state для защиты от CSRF"""
    return secrets.token_urlsafe(32)


@router.get("/auth/yandex")
async def auth_yandex():
    """Начало авторизации через Яндекс (с правами на почту)"""
    state = generate_state()

    # Если агент только читает письма, можно заменить на mail:imap_ro
    scope = "login:email login:info mail:imap_full"

    params = {
        "response_type": "code",
        "client_id": settings.yandex_client_id,
        "redirect_uri": settings.yandex_redirect_uri,
        "state": state,
        "scope": scope,
    }

    auth_url = f"{settings.yandex_auth_url}?{urlencode(params)}"
    response = RedirectResponse(url=auth_url)

    response.set_cookie(
        key="oauth_state",
        value=state,
        httponly=True,
        max_age=300,
        samesite="lax",
        secure=False,
        path="/",
    )

    response.set_cookie(
        key="oauth_state_debug",
        value=state,
        httponly=False,
        max_age=300,
        samesite="lax",
        secure=False,
        path="/",
    )

    print("=== НАЧАЛО АВТОРИЗАЦИИ ===")
    print(f"Установлена кука oauth_state: {state}")
    print(f"Редирект на Яндекс: {auth_url}")

    return response


@router.get("/callback")
async def auth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    """Обработка callback от Яндекса"""

    print("\n=== НАЧАЛО CALLBACK ===")
    print(f"Все параметры запроса: {dict(request.query_params)}")
    print(f"Все куки запроса: {request.cookies}")
    print(f"Code: {code}")
    print(f"State из URL: {state}")

    if error:
        print(f"Яндекс вернул ошибку: {error}")
        return {"error": f"Яндекс вернул ошибку: {error}"}

    if not code:
        print("Нет code в запросе")
        return {"error": "No code provided"}

    # TODO: в проде вернуть строгую проверку state
    print("⚠️ РЕЖИМ ОТЛАДКИ: пропускаем проверку state")
    print(f"State из URL: {state}")
    print(f"State из куки oauth_state: {request.cookies.get('oauth_state')}")
    print(f"State из куки oauth_state_debug: {request.cookies.get('oauth_state_debug')}")

    async with httpx.AsyncClient(timeout=20.0) as client:
        print("Отправляем запрос на получение токена...")
        print(f"Client ID: {settings.yandex_client_id}")
        print(f"Redirect URI: {settings.yandex_redirect_uri}")

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
            error_text = token_response.text
            print(f"Ошибка получения токена: {error_text}")
            return {"error": f"Failed to get token: {error_text}"}

        token_data = token_response.json()
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = int(token_data.get("expires_in") or 0)

        if not access_token:
            print("Нет access_token в ответе")
            return {"error": "No access token in response"}

        if not refresh_token:
            print("⚠️ Нет refresh_token в ответе — mail-agent не сможет долго обновлять токен автоматически")
        else:
            print("✓ Получен refresh_token")

        access_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in or 3600)

        print("✓ Токен получен успешно")
        print(f"expires_in: {expires_in}")
        print(f"access_expires_at: {access_expires_at.isoformat()}")

        print("Запрашиваем информацию о пользователе...")
        user_response = await client.get(
            settings.yandex_user_info_url,
            params={"format": "json"},
            headers={"Authorization": f"OAuth {access_token}"},
        )

        if user_response.status_code != 200:
            error_text = user_response.text
            print(f"Ошибка получения данных пользователя: {error_text}")
            return {"error": f"Failed to get user info: {error_text}"}

        user_data = user_response.json()
        print(f"Данные пользователя получены: {user_data.get('default_email')}")

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
            print(f"Ошибка работы с БД users: {e}")
            return {"error": "Failed to sync user with database"}

        try:
            await update_user_mail_tokens(
                user_id=db_user["id"],
                access_token=access_token,
                refresh_token=refresh_token,
                access_expires_at=access_expires_at,
            )
            print(f"✓ Почтовые токены сохранены для user_id={db_user['id']}")
        except Exception as e:
            print(f"Ошибка сохранения почтовых токенов: {e}")
            return {"error": "Failed to save mail tokens"}

        session_id = generate_state()
        sessions[session_id] = {
            "id": db_user["id"],
            "email": db_user["email"],
            "name": name,
            "login": db_user["login"],
            "role": db_user["role"],
        }

        print(f"✓ Сессия создана: {session_id}")
        print(f"Пользователь (app): {sessions[session_id]}")
        print(f"Всего сессий: {len(sessions)}")

        print("Перенаправляем на главную страницу...")
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            max_age=86400,
            samesite="lax",
            secure=False,
            path="/",
        )

        response.delete_cookie(key="oauth_state", path="/")
        response.delete_cookie(key="oauth_state_debug", path="/")

        print("=== КОНЕЦ CALLBACK ===\n")
        return response


@router.get("/logout")
async def logout(request: Request):
    """Выход из системы"""
    session_id = request.cookies.get("session_id")
    print(f"Выход: session_id = {session_id}")

    if session_id and session_id in sessions:
        del sessions[session_id]
        print(f"Сессия {session_id} удалена")

    response = RedirectResponse(url="/login")
    response.delete_cookie(key="session_id")
    return response


def get_current_user(request: Request):
    """Получение текущего пользователя из сессии"""
    session_id = request.cookies.get("session_id")
    print(f"get_current_user: session_id = {session_id}")

    if session_id and session_id in sessions:
        user = sessions[session_id]
        print(f"Найден пользователь: {user['email']}")
        return user

    print("Пользователь не найден")
    return None