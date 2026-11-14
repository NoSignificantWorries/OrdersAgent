BEGIN;

-- Избранные почты
CREATE TABLE IF NOT EXISTS favorite_senders (
    id BIGSERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT favorite_senders_email_not_empty_chk
        CHECK (BTRIM(email) <> ''),

    CONSTRAINT favorite_senders_email_trimmed_chk
        CHECK (email = BTRIM(email))
);

-- Уникальность адресов без учёта регистра
CREATE UNIQUE INDEX IF NOT EXISTS uq_favorite_senders_email_lower
    ON favorite_senders (LOWER(email));

COMMIT;