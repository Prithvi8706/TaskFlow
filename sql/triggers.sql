-- =====================================================================
-- TaskFlow triggers (PostgreSQL)
-- Applied by migration tracker/0010_triggers. Safe to re-run.
-- =====================================================================


-- ---------------------------------------------------------------------
-- 1. trg_task_status_history
--    AFTER INSERT OR UPDATE OF status ON task
--    Writes an audit row to task_history:
--      * on INSERT : (NULL -> new status)
--      * on UPDATE : only when the status really changed
--    task_history is written ONLY by this trigger.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_task_status_history()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO task_history (task_id, old_status, new_status, changed_at)
        VALUES (NEW.task_id, NULL, NEW.status, clock_timestamp());
    ELSIF OLD.status IS DISTINCT FROM NEW.status THEN
        INSERT INTO task_history (task_id, old_status, new_status, changed_at)
        VALUES (NEW.task_id, OLD.status, NEW.status, clock_timestamp());
    END IF;
    RETURN NULL;  -- result is ignored for AFTER triggers
END;
$$;

DROP TRIGGER IF EXISTS trg_task_status_history ON task;
CREATE TRIGGER trg_task_status_history
    AFTER INSERT OR UPDATE OF status ON task
    FOR EACH ROW
    EXECUTE FUNCTION fn_task_status_history();


-- ---------------------------------------------------------------------
-- 2. trg_task_completed_at
--    BEFORE INSERT OR UPDATE ON task
--    Keeps completed_at consistent with status:
--      * status becomes COMPLETED      -> completed_at = now()
--      * status leaves COMPLETED       -> completed_at = NULL
--      * stays COMPLETED               -> keep the original timestamp
--    INSERT is covered too, so a task created as COMPLETED is stamped.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_task_completed_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.status = 'COMPLETED' THEN
        IF TG_OP = 'INSERT' THEN
            NEW.completed_at := COALESCE(NEW.completed_at, now());
        ELSIF OLD.status IS DISTINCT FROM 'COMPLETED' THEN
            NEW.completed_at := now();
        ELSE
            NEW.completed_at := COALESCE(NEW.completed_at, OLD.completed_at, now());
        END IF;
    ELSE
        NEW.completed_at := NULL;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_task_completed_at ON task;
CREATE TRIGGER trg_task_completed_at
    BEFORE INSERT OR UPDATE ON task
    FOR EACH ROW
    EXECUTE FUNCTION fn_task_completed_at();
