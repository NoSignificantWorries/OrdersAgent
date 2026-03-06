CREATE TABLE IF NOT EXISTS users (
  id BIGSERIAL PRIMARY KEY,
  login VARCHAR(50) UNIQUE NOT NULL,
  email VARCHAR(255) UNIQUE NOT NULL,
  pass_hash CHAR(60) NOT NULL,
  role VARCHAR(20) NOT NULL DEFAULT 'manager',
  current_load INT DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS process_queue (
  id BIGSERIAL PRIMARY KEY,
  assigned_to BIGINT NOT NULL REFERENCES users(id) ON DELETE SET NULL,
  email_subject VARCHAR(255),
  email_body TEXT,
  document_name VARCHAR(255),
  document_data BYTEA,
  result_document_name VARCHAR(255),
  result_document_data BYTEA,
  status VARCHAR(20) NOT NULL DEFAULT 'wait',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

