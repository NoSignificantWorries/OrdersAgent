ALTER TYPE task_status ADD VALUE IF NOT EXISTS 'claim' AFTER 'question';

CREATE INDEX IF NOT EXISTS idx_tasks_claim
    ON tasks(status, created_at)
    WHERE status = 'claim';