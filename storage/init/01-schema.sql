-- ============================================
-- 1. ENUM для статусов задач
-- ============================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'task_status') THEN
        CREATE TYPE task_status AS ENUM (
            'new',
            'downloaded',
            'files_saved',
            'ml_processing',
            'ml_classified',
            'question',
            'ml_review',
            'materials_review',
            'manual_review_done',
            'completed',
            'error'
        );
    END IF;
END$$;


-- ============================================
-- 2. ТАБЛИЦЫ
-- ============================================

-- Пользователи
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    login VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    pass_hash CHAR(60) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'standart',
    mail_access_token TEXT,
    mail_refresh_token TEXT,
    mail_access_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Маппинг материалов
CREATE TABLE IF NOT EXISTS mappings (
    source VARCHAR(255) PRIMARY KEY,
    target VARCHAR(255),
    article VARCHAR(255),
    black_list BOOLEAN NOT NULL DEFAULT FALSE
);

-- Письма
CREATE TABLE IF NOT EXISTS emails (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    mailbox VARCHAR(100) NOT NULL,
    email_uid BIGINT NOT NULL,
    message_id TEXT,
    in_reply_to TEXT,
    references_header TEXT,
    email_from TEXT,
    reply_to TEXT,
    email_subject VARCHAR(500),
    raw_email TEXT,
    email_date TIMESTAMPTZ,
    prob_1 DOUBLE PRECISION,
    predicted_class SMALLINT,
    model_decision TEXT,
    archived BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE(mailbox, email_uid)
);

-- Вложения
CREATE TABLE IF NOT EXISTS documents (
    id BIGSERIAL PRIMARY KEY,
    email_id BIGINT NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
    filename VARCHAR(500),
    minio_object_key TEXT,
    content_type VARCHAR(100),
    size_bytes BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Задачи
CREATE TABLE IF NOT EXISTS tasks (
    id BIGSERIAL PRIMARY KEY,
    email_id BIGINT NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
    document_id BIGINT REFERENCES documents(id) ON DELETE SET NULL,

    status task_status NOT NULL DEFAULT 'new',

    -- Результаты ML и парсинга
    output_data JSONB DEFAULT '{}',

    -- Ручное решение пользователя
    manual_decision JSONB,

    -- Кто взял задачу (для связи с users)
    assigned_to BIGINT REFERENCES users(id) ON DELETE SET NULL,

    -- Трекинг ошибок
    error_message TEXT,
    retry_count INT DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);


-- ============================================
-- 3. ИНДЕКСЫ
-- ============================================

-- Планировщик: получить задачи на обработку
CREATE INDEX IF NOT EXISTS idx_tasks_pending
    ON tasks(status, created_at)
    WHERE status IN ('new', 'downloaded', 'files_saved', 'manual_review_done');

-- WebUI: задачи, ожидающие ручного вмешательства
CREATE INDEX IF NOT EXISTS idx_tasks_manual
    ON tasks(status, created_at)
    WHERE status IN ('ml_review', 'materials_review');

-- WebUI: задачи конкретного пользователя
CREATE INDEX IF NOT EXISTS idx_tasks_assigned
    ON tasks(assigned_to, status, created_at)
    WHERE assigned_to IS NOT NULL;

-- Поиск задач по письму
CREATE INDEX IF NOT EXISTS idx_tasks_email_id
    ON tasks(email_id);

-- Мониторинг зависших задач
CREATE INDEX IF NOT EXISTS idx_tasks_stale
    ON tasks(updated_at)
    WHERE status NOT IN ('completed', 'error');

-- Поля для определения основного получателя
ALTER TABLE emails ADD COLUMN IF NOT EXISTS to_header TEXT;
ALTER TABLE emails ADD COLUMN IF NOT EXISTS cc_header TEXT;
ALTER TABLE emails ADD COLUMN IF NOT EXISTS delivered_to TEXT;
ALTER TABLE emails ADD COLUMN IF NOT EXISTS x_original_to TEXT;
ALTER TABLE emails ADD COLUMN IF NOT EXISTS envelope_to TEXT;
ALTER TABLE emails ADD COLUMN IF NOT EXISTS x_envelope_to TEXT;
ALTER TABLE emails ADD COLUMN IF NOT EXISTS recipient_email TEXT;
ALTER TABLE emails ADD COLUMN IF NOT EXISTS recipient_source TEXT;
ALTER TABLE emails ADD COLUMN IF NOT EXISTS is_primary_recipient BOOLEAN DEFAULT FALSE;

-- Индекс для быстрой фильтрации
CREATE INDEX IF NOT EXISTS idx_emails_primary_recipient 
    ON emails(user_id, is_primary_recipient, created_at) 
    WHERE is_primary_recipient = TRUE;

-- Индекс для группировки по message_id
CREATE INDEX IF NOT EXISTS idx_emails_message_id ON emails(message_id);