BEGIN;

SET LOCAL lock_timeout = '5s';

-- Для исторических писем версия UID пока неизвестна.
-- Старое ограничение уникальности на этом этапе сохраняем.
ALTER TABLE public.emails
    ADD COLUMN IF NOT EXISTS uid_validity BIGINT;

-- Состояние восстановления INBOX, одно на пользователя.
CREATE TABLE IF NOT EXISTS public.mail_sync_state (
    user_id BIGINT PRIMARY KEY
        REFERENCES public.users(id) ON DELETE CASCADE,

    uid_validity BIGINT NOT NULL
        CHECK (uid_validity BETWEEN 1 AND 4294967295),

    last_reconciled_uid BIGINT NOT NULL
        CHECK (last_reconciled_uid BETWEEN 0 AND 4294967295),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON COLUMN public.emails.uid_validity IS
    'IMAP UIDVALIDITY папки INBOX. NULL: версия исторического письма не подтверждена.';

COMMENT ON TABLE public.mail_sync_state IS
    'Контрольные точки восстановления входящих писем из INBOX.';

COMMENT ON COLUMN public.mail_sync_state.last_reconciled_uid IS
    'Верхняя граница успешно завершённой сверки, не максимальный UID импортированного письма.';

COMMIT;