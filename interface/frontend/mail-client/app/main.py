# app/main.py
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
import os

from app.config import settings
from app.routers import auth

# Создание экземпляра приложения
app = FastAPI(
    title=settings.app_name,
    debug=settings.debug
)

# Подключение статических файлов (CSS, JS)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Настройка шаблонов
templates = Jinja2Templates(directory="app/templates")

# Подключение маршрутов авторизации
app.include_router(auth.router)

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Главная страница - только для авторизованных"""
    print(f"\n=== ГЛАВНАЯ СТРАНИЦА ===")
    print(f"Cookies: {request.cookies}")
    
    # Получаем пользователя из сессии
    user = auth.get_current_user(request)
    print(f"Пользователь: {user}")
    
    if user:
        print("Пользователь авторизован - показываем главную")
        return templates.TemplateResponse(
            "index.html", 
            {"request": request, "user": user}
        )
    else:
        print("Пользователь НЕ авторизован - редирект на /login")
        return RedirectResponse(url="/login")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Страница входа"""
    # Если уже авторизован - отправляем на главную
    user = auth.get_current_user(request)
    if user:
        print("Уже авторизован - редирект на главную")
        return RedirectResponse(url="/")
    
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/debug")
async def debug_session(request: Request):
    """Отладка - посмотреть все сессии"""
    return {
        "cookies": dict(request.cookies),
        "sessions": {k: v for k, v in auth.sessions.items()},
        "session_count": len(auth.sessions)
    }

@app.get("/test-cookie")
async def test_cookie(request: Request):
    """Тестовый маршрут для проверки установки кук"""
    from fastapi.responses import JSONResponse
    
    # Устанавливаем тестовую куку
    response = JSONResponse({
        "message": "Тестовая кука установлена",
        "cookies": dict(request.cookies)
    })
    
    response.set_cookie(
        key="test_cookie", 
        value="test_value_123", 
        httponly=True,
        max_age=60,
        samesite="lax",
        secure=False,
        path="/"
    )
    
    return response

# Для запуска напрямую
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )