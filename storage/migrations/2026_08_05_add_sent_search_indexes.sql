CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_sent_emails_subject_trgm
    ON sent_emails
    USING gin (email_subject gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_sent_emails_to_header_trgm
    ON sent_emails
    USING gin (to_header gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_sent_emails_from_trgm
    ON sent_emails
    USING gin (email_from gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_sent_emails_raw_email_trgm
    ON sent_emails
    USING gin (raw_email gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_sent_emails_mailbox_sent_at
    ON sent_emails (
        mailbox,
        sent_at DESC,
        id DESC
    );