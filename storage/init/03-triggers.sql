DROP TRIGGER IF EXISTS trigger_auto_assign_manager ON process_queue;
CREATE TRIGGER trigger_auto_assign_manager
    BEFORE INSERT ON process_queue
    FOR EACH ROW
    EXECUTE FUNCTION auto_assign_manager();

DROP TRIGGER IF EXISTS trigger_complete_task ON process_queue;
CREATE TRIGGER trigger_complete_task
    AFTER UPDATE OF status ON process_queue
    FOR EACH ROW
    WHEN (NEW.status IN ('completed', 'failed') AND OLD.status = 'processing')
    EXECUTE FUNCTION complete_task();

