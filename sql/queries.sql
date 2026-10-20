-- =====================================================================
-- TaskFlow analytical queries (PostgreSQL)
--
-- Run after `python manage.py seed_demo`, from the project root:
--   docker exec -i taskflow-db psql -U taskflow -d taskflow < sql/queries.sql
--
-- Every query is scoped to one user through :owner_id. Q8 and Q13 also
-- take :task_id. In psql both are set below; the Analytics page parses
-- this same file and binds them as query parameters (%(owner_id)s), so
-- the SQL on screen is exactly the SQL in this file.
--
-- Block format read by the app:  -- [Qn] Title / -- Answers: / -- Concepts:
-- =====================================================================

\set owner_id '(SELECT id FROM auth_user WHERE username = ''demo'')'
\set task_id '(SELECT t.task_id FROM task t JOIN project p ON p.project_id = t.project_id JOIN auth_user u ON u.id = p.owner_id WHERE u.username = ''demo'' AND t.title = ''Colour and type tokens'')'


-- [Q1] Projects with total and completed task counts
-- Answers: How many tasks does each project have, and how many are done?
-- Concepts: LEFT JOIN, GROUP BY, COUNT with FILTER
SELECT p.project_id,
       p.name                                                 AS project,
       p.status,
       COUNT(t.task_id)                                       AS total_tasks,
       COUNT(t.task_id) FILTER (WHERE t.status = 'COMPLETED') AS completed_tasks
FROM project p
LEFT JOIN task t ON t.project_id = p.project_id
WHERE p.owner_id = :owner_id
GROUP BY p.project_id, p.name, p.status
ORDER BY p.name;


-- [Q2] Completion percentage per project
-- Answers: What share of each project's tasks is complete, and what stage is it in?
-- Concepts: CASE expression, SUM/COUNT aggregates, NULLIF to avoid divide-by-zero, derived table
SELECT project,
       total_tasks,
       completed_tasks,
       completion_pct,
       CASE
           WHEN completion_pct >= 75 THEN 'Nearly done'
           WHEN completion_pct >= 40 THEN 'Underway'
           ELSE 'Early stage'
       END AS stage
FROM (
    SELECT p.name                                                      AS project,
           COUNT(t.task_id)                                            AS total_tasks,
           SUM(CASE WHEN t.status = 'COMPLETED' THEN 1 ELSE 0 END)     AS completed_tasks,
           COALESCE(ROUND(100.0 * SUM(CASE WHEN t.status = 'COMPLETED' THEN 1 ELSE 0 END)
                          / NULLIF(COUNT(t.task_id), 0), 1), 0)        AS completion_pct
    FROM project p
    LEFT JOIN task t ON t.project_id = p.project_id
    WHERE p.owner_id = :owner_id
    GROUP BY p.project_id, p.name
) per_project
ORDER BY completion_pct DESC, project;


-- [Q3] Overdue incomplete tasks
-- Answers: Which unfinished tasks are past their deadline, and by how many days?
-- Concepts: date filtering with CURRENT_DATE, date subtraction, JOIN
SELECT t.task_id,
       t.title,
       p.name                     AS project,
       t.priority,
       t.status,
       t.deadline,
       CURRENT_DATE - t.deadline  AS days_overdue
FROM task t
JOIN project p ON p.project_id = t.project_id
WHERE p.owner_id = :owner_id
  AND t.status <> 'COMPLETED'
  AND t.deadline < CURRENT_DATE
ORDER BY days_overdue DESC, t.title;


-- [Q4] Task counts by status and priority
-- Answers: How is the workload spread across status and priority combinations?
-- Concepts: GROUP BY two columns, CASE in ORDER BY for a custom sort
SELECT t.status,
       t.priority,
       COUNT(*) AS tasks
FROM task t
JOIN project p ON p.project_id = t.project_id
WHERE p.owner_id = :owner_id
GROUP BY t.status, t.priority
ORDER BY CASE t.status WHEN 'PENDING' THEN 1 WHEN 'IN_PROGRESS' THEN 2 WHEN 'BLOCKED' THEN 3 ELSE 4 END,
         CASE t.priority WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END;


-- [Q5] Categories with the most tasks
-- Answers: Which five categories carry the most tasks?
-- Concepts: LEFT JOIN, GROUP BY, ORDER BY ... DESC, LIMIT
SELECT c.name           AS category,
       COUNT(t.task_id) AS tasks
FROM category c
LEFT JOIN task t ON t.category_id = c.category_id
WHERE c.owner_id = :owner_id
GROUP BY c.category_id, c.name
ORDER BY tasks DESC, c.name
LIMIT 5;


-- [Q6] Milestones with completion percentage
-- Answers: How far along is each milestone?
-- Concepts: querying a VIEW (v_milestone_progress), JOIN to base tables
SELECT p.name            AS project,
       v.name            AS milestone,
       m.deadline,
       m.status,
       v.total_tasks,
       v.completed_tasks,
       v.completion_pct
FROM v_milestone_progress v
JOIN milestone m ON m.milestone_id = v.milestone_id
JOIN project p   ON p.project_id = v.project_id
WHERE p.owner_id = :owner_id
ORDER BY p.name, m.deadline;


-- [Q7] Projects with more than five incomplete tasks
-- Answers: Which projects have a backlog of more than five open tasks?
-- Concepts: WHERE filters rows before grouping, HAVING filters groups after
SELECT p.name   AS project,
       COUNT(*) AS incomplete_tasks
FROM project p
JOIN task t ON t.project_id = p.project_id
WHERE p.owner_id = :owner_id
  AND t.status <> 'COMPLETED'
GROUP BY p.project_id, p.name
HAVING COUNT(*) > 5
ORDER BY incomplete_tasks DESC, project;


-- [Q8] Status history of a task in chronological order
-- Answers: What path did one task take through its statuses, and when?
-- Concepts: rows written by trigger trg_task_status_history, JOIN, ORDER BY timestamp
SELECT t.title,
       h.old_status,
       h.new_status,
       h.changed_at
FROM task_history h
JOIN task t    ON t.task_id = h.task_id
JOIN project p ON p.project_id = t.project_id
WHERE h.task_id = :task_id
  AND p.owner_id = :owner_id
ORDER BY h.changed_at, h.history_id;


-- [Q9] Tasks whose prerequisites are not yet completed
-- Answers: Which unfinished tasks are waiting on other unfinished tasks?
-- Concepts: EXISTS subquery, correlated subquery with STRING_AGG
SELECT t.title,
       p.name   AS project,
       t.status,
       (SELECT STRING_AGG(pre.title, ', ' ORDER BY pre.title)
        FROM task_dependency d2
        JOIN task pre ON pre.task_id = d2.depends_on_task_id
        WHERE d2.task_id = t.task_id
          AND pre.status <> 'COMPLETED')   AS waiting_on
FROM task t
JOIN project p ON p.project_id = t.project_id
WHERE p.owner_id = :owner_id
  AND t.status <> 'COMPLETED'
  AND EXISTS (
        SELECT 1
        FROM task_dependency d
        JOIN task pre ON pre.task_id = d.depends_on_task_id
        WHERE d.task_id = t.task_id
          AND pre.status <> 'COMPLETED'
  )
ORDER BY project, t.title;


-- [Q10] Project with the most overdue tasks
-- Answers: Which project has the most overdue tasks? (all of them, if tied)
-- Concepts: nested subquery in HAVING compared against MAX of a derived table; ties are kept, unlike LIMIT 1
SELECT p.name   AS project,
       COUNT(*) AS overdue_tasks
FROM project p
JOIN task t ON t.project_id = p.project_id
WHERE p.owner_id = :owner_id
  AND t.status <> 'COMPLETED'
  AND t.deadline < CURRENT_DATE
GROUP BY p.project_id, p.name
HAVING COUNT(*) = (
    SELECT MAX(overdue)
    FROM (
        SELECT COUNT(*) AS overdue
        FROM task t2
        JOIN project p2 ON p2.project_id = t2.project_id
        WHERE p2.owner_id = :owner_id
          AND t2.status <> 'COMPLETED'
          AND t2.deadline < CURRENT_DATE
        GROUP BY t2.project_id
    ) per_project
)
ORDER BY project;


-- [Q11] Average days taken to complete a task
-- Answers: How long do tasks take from creation to completion, per project and overall?
-- Concepts: timestamp arithmetic (completed_at - created_at), EXTRACT(EPOCH), AVG, GROUP BY ROLLUP
SELECT COALESCE(p.name, 'All projects')                                       AS project,
       COUNT(*)                                                               AS completed_tasks,
       ROUND(AVG(EXTRACT(EPOCH FROM (t.completed_at - t.created_at)) / 86400)::numeric, 1)
                                                                              AS avg_days,
       MIN(t.completed_at::date - t.created_at::date)                         AS fastest_days,
       MAX(t.completed_at::date - t.created_at::date)                         AS slowest_days
FROM task t
JOIN project p ON p.project_id = t.project_id
WHERE p.owner_id = :owner_id
  AND t.completed_at IS NOT NULL
GROUP BY ROLLUP (p.name)
ORDER BY GROUPING(p.name), avg_days DESC;


-- [Q12] Projects above the overall average completion
-- Answers: Which projects are doing better than the user's average project?
-- Concepts: nested scalar subquery in WHERE and SELECT, querying v_project_progress
SELECT v.name            AS project,
       v.completion_pct,
       (SELECT ROUND(AVG(v2.completion_pct), 1)
        FROM v_project_progress v2
        WHERE v2.owner_id = :owner_id)  AS average_pct
FROM v_project_progress v
WHERE v.owner_id = :owner_id
  AND v.completion_pct > (
        SELECT AVG(v2.completion_pct)
        FROM v_project_progress v2
        WHERE v2.owner_id = :owner_id
  )
ORDER BY v.completion_pct DESC;


-- [Q13] Full prerequisite chain of a task
-- Answers: Everything that must be finished (directly or indirectly) before this task can start
-- Concepts: WITH RECURSIVE (anchor + recursive member), path array as a cycle guard, DISTINCT ON
WITH RECURSIVE chain AS (
    -- anchor: direct prerequisites of the chosen task
    SELECT d.depends_on_task_id                 AS task_id,
           1                                    AS depth,
           ARRAY[d.task_id, d.depends_on_task_id] AS path
    FROM task_dependency d
    WHERE d.task_id = :task_id
    UNION ALL
    -- recursive member: prerequisites of the prerequisites
    SELECT d.depends_on_task_id,
           c.depth + 1,
           c.path || d.depends_on_task_id
    FROM chain c
    JOIN task_dependency d ON d.task_id = c.task_id
    WHERE d.depends_on_task_id <> ALL (c.path)
)
SELECT depth, title, status, via
FROM (
    SELECT DISTINCT ON (c.task_id)
           c.depth,
           t.title,
           t.status,
           (SELECT STRING_AGG(pt.title, ' → ' ORDER BY u.ord)
            FROM UNNEST(c.path) WITH ORDINALITY AS u(id, ord)
            JOIN task pt ON pt.task_id = u.id) AS via
    FROM chain c
    JOIN task t    ON t.task_id = c.task_id
    JOIN project p ON p.project_id = t.project_id
    WHERE p.owner_id = :owner_id
    ORDER BY c.task_id, c.depth
) shortest
ORDER BY depth, title;
