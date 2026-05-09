-- ============================================
-- 1. ENUM ТИПЫ (создаем до таблиц!)
-- ============================================

-- Проверяем существование перед созданием
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'task_type') THEN
        CREATE TYPE task_type AS ENUM (
            'classify_email',
            'manual_classify',
            'parse_documents',
            'manual_identify_materials',
            'reparse_with_manual_input'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'task_status') THEN
        CREATE TYPE task_status AS ENUM (
            'pending',
            'in_progress',
            'awaiting_user',
            'completed',
            'failed',
            'skipped'
        );
    END IF;
END$$;

-- ============================================
-- 2. ТАБЛИЦЫ
-- ============================================

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    login VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    pass_hash CHAR(60) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'manager',
    current_load INT DEFAULT 0,
    mail_access_token TEXT,
    mail_refresh_token TEXT,
    mail_access_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Письма и их метаданные
CREATE TABLE IF NOT EXISTS emails (
    id BIGSERIAL PRIMARY KEY,
    target_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    email_uid BIGINT UNIQUE,  -- уникальный идентификатор письма в почтовом ящике
    email_from TEXT,
    email_subject VARCHAR(255),
    email_body TEXT,
    email_date TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Документы (отдельно от писем)
CREATE TABLE IF NOT EXISTS documents (
    id BIGSERIAL PRIMARY KEY,
    email_id BIGINT NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
    document_name VARCHAR(255),
    object_bucket TEXT,
    object_key TEXT,
    document_data BYTEA,
    result_document_name VARCHAR(255),
    result_document_data BYTEA,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ЗАДАЧИ (сквозная очередь) — теперь типы ENUM существуют
CREATE TABLE IF NOT EXISTS tasks (
    id BIGSERIAL PRIMARY KEY,
    email_id BIGINT NOT NULL REFERENCES emails(id) ON DELETE CASCADE,

    -- Тип задачи
    type task_type NOT NULL,

    -- Статус задачи
    status task_status NOT NULL DEFAULT 'pending',

    -- Приоритет (чем меньше число, тем выше приоритет)
    priority INT DEFAULT 100,

    -- Кто обрабатывает
    assigned_to BIGINT REFERENCES users(id) ON DELETE SET NULL,

    -- Данные для задачи (гибкий JSON)
    input_data JSONB DEFAULT '{}',

    -- Результаты (включая классификацию)
    output_data JSONB DEFAULT '{}',

    -- Метаданные выполнения
    attempts INT DEFAULT 0,
    max_attempts INT DEFAULT 3,
    error_message TEXT,

    -- Тайминги
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

-- ============================================
-- 3. ИНДЕКСЫ
-- ============================================

-- Основной индекс для получения следующей задачи
CREATE INDEX IF NOT EXISTS idx_tasks_next
    ON tasks(priority, created_at)
    WHERE status = 'pending';

-- Индекс для воркеров
CREATE INDEX IF NOT EXISTS idx_tasks_type_pending
    ON tasks(type, priority, created_at)
    WHERE status = 'pending';

-- Индекс для поиска задач, ожидающих пользователя
CREATE INDEX IF NOT EXISTS idx_tasks_awaiting
    ON tasks(assigned_to, created_at)
    WHERE status = 'awaiting_user';

-- Предотвращение зависших задач (мониторинг)
CREATE INDEX IF NOT EXISTS idx_tasks_stuck
    ON tasks(started_at)
    WHERE status = 'in_progress';

-- Быстрый поиск по email_id
CREATE INDEX IF NOT EXISTS idx_tasks_email
    ON tasks(email_id, status);
