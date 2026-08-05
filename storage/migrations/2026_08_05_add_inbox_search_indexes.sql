CREATE INDEX IF NOT EXISTS idx_emails_mailbox_archived_sort
    ON emails (
        mailbox,
        archived,
        COALESCE(email_date, created_at) DESC,
        id DESC
    );

CREATE INDEX IF NOT EXISTS idx_emails_subject_trgm
    ON emails
    USING gin (email_subject gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_emails_from_trgm
    ON emails
    USING gin (email_from gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_emails_mailbox_trgm
    ON emails
    USING gin (mailbox gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_emails_raw_email_trgm
    ON emails
    USING gin (raw_email gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_tasks_email_id_created_at
    ON tasks (email_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_documents_email_id
    ON documents (email_id);