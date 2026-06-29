-- Таблица исходящих
CREATE TABLE IF NOT EXISTS sent_emails (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    mailbox VARCHAR(100) NOT NULL,
    email_uid BIGINT,
    message_id TEXT,
    in_reply_to TEXT,
    references_header TEXT,
    parent_email_id BIGINT REFERENCES emails(id) ON DELETE SET NULL,
    email_from TEXT,
    reply_to TEXT,
    to_header TEXT,
    cc_header TEXT,
    bcc_header TEXT,
    email_subject VARCHAR(500),
    raw_email TEXT,
    email_date TIMESTAMPTZ,
    send_status VARCHAR(20) NOT NULL DEFAULT 'sent',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    sent_at TIMESTAMPTZ DEFAULT NOW()
);

-- Ограничение на значения send_status
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'sent_emails'
    ) AND NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'sent_emails_send_status_chk'
    ) THEN
        ALTER TABLE sent_emails
        ADD CONSTRAINT sent_emails_send_status_chk
        CHECK (send_status IN ('pending', 'sent', 'failed'));
    END IF;
END$$;

-- Вложения исходящих
CREATE TABLE IF NOT EXISTS sent_documents (
    id BIGSERIAL PRIMARY KEY,
    sent_email_id BIGINT NOT NULL REFERENCES sent_emails(id) ON DELETE CASCADE,
    filename VARCHAR(500),
    minio_object_key TEXT,
    content_type VARCHAR(100),
    size_bytes BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Уникальность UID внутри mailbox, если UID известен
CREATE UNIQUE INDEX IF NOT EXISTS uq_sent_emails_mailbox_uid
    ON sent_emails(mailbox, email_uid)
    WHERE email_uid IS NOT NULL;

-- Поиск по threading-заголовкам
CREATE INDEX IF NOT EXISTS idx_sent_emails_message_id
    ON sent_emails(message_id);

CREATE INDEX IF NOT EXISTS idx_sent_emails_in_reply_to
    ON sent_emails(in_reply_to);

CREATE INDEX IF NOT EXISTS idx_sent_emails_parent_email_id
    ON sent_emails(parent_email_id);

-- История отправленных пользователем
CREATE INDEX IF NOT EXISTS idx_sent_emails_user_created
    ON sent_emails(user_id, created_at DESC);

-- Выборки по ящику
CREATE INDEX IF NOT EXISTS idx_sent_emails_mailbox_sent_at
    ON sent_emails(mailbox, sent_at DESC);

-- Вложения исходящих по письму
CREATE INDEX IF NOT EXISTS idx_sent_documents_sent_email_id
    ON sent_documents(sent_email_id);