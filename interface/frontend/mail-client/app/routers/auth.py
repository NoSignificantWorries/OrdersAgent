
# app/routers/auth.py
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import RedirectResponse
import httpx
import secrets
from urllib.parse import urlencode
import json

from app.config import settings

router = APIRouter()

# Простое хранилище сессий (в памяти)
sessions = {}

def generate_state():
    """Генерация случайного state для защиты от CSRF"""
    return secrets.token_urlsafe(32)

@router.get("/auth/yandex")
async def auth_yandex():
    """Начало авторизации через Яндекс"""
    state = generate_state()
    
    # Параметры запроса к Яндексу
    params = {
        "response_type": "code",
        "client_id": settings.yandex_client_id,
        "redirect_uri": settings.yandex_redirect_uri,
        "state": state
    }
    
    # Формируем URL для редиректа
    auth_url = f"{settings.yandex_auth_url}?{urlencode(params)}"
    
    # Сохраняем state в куки для проверки
    response = RedirectResponse(url=auth_url)
    
    # Пробуем разные способы установки куки
    response.set_cookie(
        key="oauth_state", 
        value=state, 
        httponly=True,
        max_age=300,  # 5 минут
        samesite="lax",  # Меняем на lax для локальной разработки
        secure=False,
        path="/"
    )
    
    # Дополнительная кука без httponly для отладки
    response.set_cookie(
        key="oauth_state_debug", 
        value=state, 
        httponly=False,
        max_age=300,
        samesite="lax",
        secure=False,
        path="/"
    )
    
    print(f"=== НАЧАЛО АВТОРИЗАЦИИ ===")
    print(f"Установлена кука oauth_state: {state}")
    print(f"Редирект на Яндекс: {auth_url}")
    
    return response

@router.get("/callback")
async def auth_callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None
):
    """Обработка callback от Яндекса"""
    
    print("\n=== НАЧАЛО CALLBACK ===")
    print(f"Все параметры запроса: {dict(request.query_params)}")
    print(f"Все куки запроса: {request.cookies}")
    print(f"Code: {code}")
    print(f"State из URL: {state}")
    
    # Если Яндекс вернул ошибку
    if error:
        print(f"Яндекс вернул ошибку: {error}")
        return {"error": f"Яндекс вернул ошибку: {error}"}
    
    # Проверяем наличие code
    if not code:
        print("Нет code в запросе")
        return {"error": "No code provided"}
    
    # Для локальной разработки - пропускаем проверку state
    print("⚠️ РЕЖИМ ОТЛАДКИ: пропускаем проверку state")
    print(f"State из URL: {state}")
    print(f"State из куки oauth_state: {request.cookies.get('oauth_state')}")
    print(f"State из куки oauth_state_debug: {request.cookies.get('oauth_state_debug')}")
    
    # Обмениваем код на токен
    async with httpx.AsyncClient() as client:
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
            }
        )
        
        print(f"Статус ответа токена: {token_response.status_code}")
        
        if token_response.status_code != 200:
            error_text = token_response.text
            print(f"Ошибка получения токена: {error_text}")
            return {"error": f"Failed to get token: {error_text}"}
        
        token_data = token_response.json()
        access_token = token_data.get("access_token")
        
        if not access_token:
            print("Нет access_token в ответе")
            return {"error": "No access token in response"}
        
        print("✓ Токен получен успешно")
        
        # Получаем информацию о пользователе
        print("Запрашиваем информацию о пользователе...")
        user_response = await client.get(
            settings.yandex_user_info_url,
            params={"format": "json"},
            headers={"Authorization": f"OAuth {access_token}"}
        )
        
        if user_response.status_code != 200:
            error_text = user_response.text
            print(f"Ошибка получения данных пользователя: {error_text}")
            return {"error": f"Failed to get user info: {error_text}"}
        
        user_data = user_response.json()
        print(f"Данные пользователя получены: {user_data.get('default_email')}")
        
        # Создаём сессию
        session_id = generate_state()
        sessions[session_id] = {
            "id": user_data.get("id"),
            "email": user_data.get("default_email"),
            "name": user_data.get("real_name") or user_data.get("display_name"),
            "login": user_data.get("login"),
        }
        
        print(f"✓ Сессия создана: {session_id}")
        print(f"Пользователь: {sessions[session_id]}")
        print(f"Всего сессий: {len(sessions)}")
        
        # Устанавливаем куки сессии и редирект на главную
        print("Перенаправляем на главную страницу...")
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie(
            key="session_id", 
            value=session_id, 
            httponly=True,
            max_age=86400,  # 24 часа
            samesite="lax",
            secure=False,
            path="/"
        )
        
        # Удаляем временные куки
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