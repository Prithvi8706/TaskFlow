-- =====================================================================
-- TaskFlow views (PostgreSQL)
-- Applied by migration tracker/0011_progress_views. Safe to re-run.
-- Both are mapped to unmanaged Django models (managed = False):
--   ProjectProgress   -> v_project_progress
--   MilestoneProgress -> v_milestone_progress
-- =====================================================================


-- ---------------------------------------------------------------------
-- v_project_progress: one row per project with task counts and the
-- completion percentage. LEFT JOIN keeps projects that have no tasks.
-- owner_id is included so the app can scope rows to the logged-in user.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_project_progress AS
SELECT
    p.project_id,
    p.owner_id,
    p.name,
    COUNT(t.task_id)                                                    AS total_tasks,
    COUNT(t.task_id) FILTER (WHERE t.status = 'COMPLETED')              AS completed_tasks,
    COUNT(t.task_id) FILTER (WHERE t.status <> 'COMPLETED'
                               AND t.deadline < CURRENT_DATE)           AS overdue_tasks,
    COALESCE(
        ROUND(100.0 * COUNT(t.task_id) FILTER (WHERE t.status = 'COMPLETED')
              / NULLIF(COUNT(t.task_id), 0), 1),
        0)::numeric(5, 1)                                               AS completion_pct
FROM project p
LEFT JOIN task t ON t.project_id = p.project_id
GROUP BY p.project_id, p.owner_id, p.name;


-- ---------------------------------------------------------------------
-- v_milestone_progress: one row per milestone with task counts and the
-- completion percentage.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_milestone_progress AS
SELECT
    m.milestone_id,
    m.project_id,
    m.name,
    COUNT(t.task_id)                                                    AS total_tasks,
    COUNT(t.task_id) FILTER (WHERE t.status = 'COMPLETED')              AS completed_tasks,
    COALESCE(
        ROUND(100.0 * COUNT(t.task_id) FILTER (WHERE t.status = 'COMPLETED')
              / NULLIF(COUNT(t.task_id), 0), 1),
        0)::numeric(5, 1)                                               AS completion_pct
FROM milestone m
LEFT JOIN task t ON t.milestone_id = m.milestone_id
GROUP BY m.milestone_id, m.project_id, m.name;
