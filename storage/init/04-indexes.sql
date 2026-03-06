CREATE INDEX IF NOT EXISTS idx_queue_status ON process_queue(status);
CREATE INDEX IF NOT EXISTS idx_queue_created ON process_queue(created_at) WHERE status = 'waiting';
CREATE INDEX IF NOT EXISTS idx_queue_assigned ON process_queue(assigned_to) WHERE status = 'processing';
CREATE INDEX IF NOT EXISTS idx_users_role_load ON users(role, current_load) WHERE role = 'manager';

CREATE INDEX IF NOT EXISTS idx_queue_user ON process_queue(user_id) WHERE assigned_to IS NOT NULL;

