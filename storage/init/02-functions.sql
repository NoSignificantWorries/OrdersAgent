CREATE OR REPLACE FUNCTION get_least_loaded_manager()
RETURNS users AS $$
BEGIN
  RETURN (
    SELECT *
      FROM users
    WHERE role = 'manager'
      AND current_load = (
        SELECT COALESCE(MIN(current_load), 0)
            FROM users
          WHERE role = 'manager'
        )
      ORDER BY RANDOM()
    LIMIT 1
  );
END;
$$ LANGUAGE plpgsql;


CREATE OR REPLACE FUNCTION auto_assign_manager()
RETURNS TRIGGER AS $$
DECLARE
    manager_id BIGINT;
BEGIN
    IF NEW.user_id IS NULL THEN
        manager_id := get_least_loaded_manager();

        IF manager_id IS NOT NULL THEN
            NEW.user_id := manager_id;
            NEW.assigned_to := manager_id;
            NEW.assigned_at := NOW();
            NEW.status := 'processing';

            UPDATE users
            SET current_load = current_load + 1
            WHERE id = manager_id;
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


CREATE OR REPLACE FUNCTION assign_waiting_tasks()
RETURNS void AS $$
DECLARE
    waiting_task RECORD;
    free_manager_id BIGINT;
BEGIN
    FOR waiting_task IN
        SELECT id FROM process_queue
        WHERE status = 'waiting'
        ORDER BY created_at ASC
        FOR UPDATE SKIP LOCKED
    LOOP
        SELECT id FROM get_least_loaded_manager() INTO free_manager_id;
        EXIT WHEN free_manager_id IS NULL;

        UPDATE process_queue
        SET user_id = free_manager_id,
            assigned_to = free_manager_id,
            assigned_at = NOW(),
            status = 'processing'
        WHERE id = waiting_task.id;

        UPDATE users
        SET current_load = current_load + 1
        WHERE id = free_manager_id;
    END LOOP;
END;
$$ LANGUAGE plpgsql;


CREATE OR REPLACE FUNCTION complete_task()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status IN ('completed', 'failed') THEN
        UPDATE users
        SET current_load = current_load - 1
        WHERE id = OLD.assigned_to;

        NEW.completed_at := NOW();

        PERFORM assign_waiting_tasks();
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

