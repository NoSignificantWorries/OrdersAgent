# 📧 Почта менеджера

Веб-интерфейс для просмотра писем с авторизацией через Яндекс.

## 🚀 Быстрый старт

### 1. Установка
```bash
# Клонировать проект
git clone <url-репозитория>
cd mail-client

# Виртуальное окружение
python -m venv venv
venv\Scripts\activate      # Windows
source venv/bin/activate   # Mac/Linux

# Зависимости
pip install -r requirements.txt

# Запуск
uvicorn app.main:app --reload


# URL САЙТА 
http://localhost:8000