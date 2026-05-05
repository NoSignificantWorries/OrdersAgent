CREATE TABLE IF NOT EXISTS users (
  id BIGSERIAL PRIMARY KEY,
  login VARCHAR(50) UNIQUE NOT NULL,
  email VARCHAR(255) UNIQUE NOT NULL,
  pass_hash CHAR(60) NOT NULL,
  role VARCHAR(20) NOT NULL DEFAULT 'manager',
  current_load INT DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
/* добавлены поля:
predicted_class — итоговый класс;
prob_1 — вероятность класса 1 от модели;
model_decision — решение модели;
assigned_to — кто обрабатывает заявку;
target_user_id — на чей ящик пришло письмо.
*/
CREATE TABLE IF NOT EXISTS process_queue (
  id BIGSERIAL PRIMARY KEY,
  assigned_to BIGINT NOT NULL REFERENCES users(id) ON DELETE SET NULL,
  target_user_id BIGINT REFERENCES users(id),
  email_subject VARCHAR(255),
  email_body TEXT,
  email_uid BIGINT,
  email_from TEXT,
  email_date TIMESTAMPTZ,
  document_name VARCHAR(255),
  object_bucket TEXT,
  object_key TEXT,
  document_data BYTEA,
  result_document_name VARCHAR(255),
  result_document_data BYTEA,
  status VARCHAR(20) NOT NULL DEFAULT 'wait',
  prob_1 double precision,
  predicted_class smallint,
  model_decision text,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE INDEX IF NOT EXISTS idx_queue_status ON process_queue(status);
CREATE INDEX IF NOT EXISTS idx_queue_created ON process_queue(created_at) WHERE status = 'waiting';
CREATE INDEX IF NOT EXISTS idx_queue_assigned ON process_queue(assigned_to) WHERE status = 'processing';
CREATE INDEX IF NOT EXISTS idx_users_role_load ON users(role, current_load) WHERE role = 'manager';

CREATE INDEX IF NOT EXISTS idx_queue_user ON process_queue(user_id) WHERE assigned_to IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_queue_target_user ON process_queue(target_user_id);